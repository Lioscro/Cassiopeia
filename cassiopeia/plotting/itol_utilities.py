"""
Basic utilities that can be used to generate visualizations of tree using the
iTOL tree plotting interface. See: https://itol.embl.de/ for more information
on the iTOL software and how to create an account.
"""

import os

from typing import Tuple, Optional

from ete3 import Tree
from itolapi import Itol
from itolapi import ItolExport
from matplotlib.colors import hsv_to_rgb, rgb_to_hsv
import numpy as np
import pandas as pd
from tqdm.auto import tqdm

from cassiopeia.data import CassiopeiaTree
from cassiopeia.preprocess import utilities


class iTOLError(Exception):
    """Raises errors related to iTOL plotting
    """

    pass

def upload_and_export_itol(
    cassiopeia_tree: CassiopeiaTree,
    api_key: str,
    projectName: str,
    tree_name: str,
    export_filepath: str,
    meta_data: List[str] = [],
    allele_table: Optional[pd.DataFrame] = None,
    indel_colors: Optional[pd.DataFrame] = None,
    indel_priors: Optional[pd.DataFrame] = None,
    rect: bool = False,
    include_legend: bool = False,
    palette: List[str],
):
    """Uploads a tree to iTOL and exports it.

    This function takes in a tree, plots in with iTOL, and exports it locally.
    A user can also specify meta data and allele tables to visualize alongside
    their tree. The function requires a user to have an account with iTOL and
    must pass in an `api_key` and a `project_name`, which corresponds to one
    in the user's iTOL account.
    
    Args:
        cassiopeia_tree: A CassiopeiaTree instance, populated with a tree.
        api_key: API key linking to your iTOL account
        project_name: Project name to upload to.
        tree_name: Name of the tree. This is what the tree will be called
            within your project directory on iTOL
        export_filepath: Output file path to save your tree. Must end with
            one of the following suffixes: ['png', 'svg', 'eps', 'ps', 'pdf'].
        meta_data: Meta data to plot alongside the tree, which must be columns
            in the CassiopeiaTree.cell_meta variable.
        allele_table: Alleletable to plot alongside the tree.
        indel_colors: Color mapping to use for plotting the alleles for each
            cell. Only necessary if `allele_table` is specified.
        indel_priors: Prior probabilities for each indel. Only useful if an
            allele table is to be plotted and `indel_colors` is None.           
        rect: Boolean indicating whether or not to save your tree as a circle
            or rectangle.
        include_legend: Plot legend along with meta data.
        palette: A palette of colors in hex format.
    """

    os.path.mkdir(".tmp/")

    with open(".tmp/tree_to_plot.tree", "w") as f:
        f.write(cassiopeia_tree.get_newick())

    file_format = export_filepath.split("/")[-1].split(".")[-1]

    if file_format not in ["png", "svg", "eps", "ps", "pdf"]:
        raise iTOLError(
            "File format must be one of " "'png', 'svg', 'eps', 'ps', 'pdf']"
        )

    itol_uploader = Itol()
    itol_uploader.add_file("tree_to_plot.tree")

    
    files = []
    if allele_table is not None:
        files += create_indel_heatmap(
            allele_table,
            cassiopeia_tree,
            f"{tree_name}.allele",
            ".tmp/",
            indel_colors,
            indel_priors,
        )

    for meta_item in meta_data:
        if meta_item not in cassiopeia_tree.cell_meta.columns:
            raise iTOLError("Meta data item not in CassiopeiaTree cell meta.")

        values = cassiopeia_tree.cell_meta[meta_item]

        if pd.api.types.is_numeric_dtype(values):
            files += create_gradient_from_df(
                values, cassiopeia_tree, f"{tree_name}.{meta_item}"
            )

        if pd.api.types.is_string_dtype(values):
            colormap = palette[:len(values.unique())]
            files += create_colorbar(
                values,
                cassiopeia_tree,
                colormap,
                f"{tree_name}.{meta_item}",
                create_legend=include_legend,
            )

    for _file in files:
        itol_uploader.add_file(_file)

    itol_uploader.params["treeName"] = tree_name
    itol_uploader.params["APIkey"] = api_key
    itol_uploader.params["projectName"] = project_name

    good_upload = itol_uploader.upload()
    if not good_upload:
        raise iTOLError(itol_uploader.comm.upload_output)

    print("iTOL output: " + str(itol_uploader.comm.upload_output))
    print("Tree Web Page URL: " + itol_uploader.get_webpage())
    print("Warnings: " + str(itol_uploader.comm.warnings))

    tree_id = itol_uploader.comm.tree_id

    itol_exporter = ItolExport()

    # set parameters:
    itol_exporter.set_export_param_value("tree", tree_id)
    itol_exporter.set_export_param_value("format", file_format)
    if rect:
        # rectangular tree settings
        itol_exporter.set_export_param_value("display_mode", 1)
    else:
        # circular tree settings
        itol_exporter.set_export_param_value("display_mode", 2)
        itol_exporter.set_export_param_value("arc", 359)
        itol_exporter.set_export_param_value("rotation", 270)

    itol_exporter.set_export_param_value("leaf_sorting", 1)
    itol_exporter.set_export_param_value("label_display", 0)
    itol_exporter.set_export_param_value("internal_marks", 0)
    itol_exporter.set_export_param_value("ignore_branch_length", 1)

    itol_exporter.set_export_param_value(
        "datasets_visible", ",".join([str(i) for i in range(len(files))])
    )

    itol_exporter.set_export_param_value("horizontal_scale_factor", 1)

    # export!
    itol_exporter.export(export_filepath)

    # remove intermediate files
    os.remove("tree_to_plot.tree")


def create_gradient_from_df(
    df: pd.DataFrame,
    tree: CassiopeiaTree,
    dataset_name: str,
    output_directory: str = "./tmp/",
    color_min: str = "#ffffff",
    color_max: str = "#000000",
):

    _leaves = tree.leaves

    if type(df) == pd.Series:
        fcols = [df.name]
    else:
        fcols = df.columns

    outfps = []
    for j in range(0, len(fcols)):

        outdf = pd.DataFrame()
        outdf["cellBC"] = _leaves
        outdf["gradient"] = df.loc[_leaves, fcols[j]].values

        header = [
            "DATASET_GRADIENT",
            "SEPARATOR TAB",
            "COLOR\t#00000",
            f"COLOR_MIN\t{color_min}",
            f"COLOR_MAX\t{color_max}",
            "MARGIN\t100",
            f"DATASET_LABEL\t{fcols[j]}",
            "STRIP_WIDTH\t50",
            "SHOW_INTERNAL\t0",
            "DATA",
            "",
        ]

        outfp = os.path.join(output_directory, f"{dataset_name}.{fcols[j]}.txt")
        with open(outfp, "w") as fOut:
            for line in header:
                fOut.write(line + "\n")
            df_writeout = outdf.to_csv(
                None, sep="\t", header=False, index=False
            )
            fOut.write(df_writeout)
        outfps.append(outfp)
    return outfps


def create_colorbar(
    labels: pd.DataFrame,
    tree: CassiopeiaTree,
    colormap: Dict[str, Tuple[float, float, float]],
    dataset_name: str,
    output_directory: str = "./.tmp/", 
    create_legend: bool = False,
):

    _leaves = tree.get_leaf_names()
    labelcolors_iTOL = []
    for i in labels.loc[_leaves].values:
        colors_i = colormap[i]
        color_i = (
            "rgb("
            + str(colors_i[0])
            + ","
            + str(colors_i[1])
            + ","
            + str(colors_i[2])
            + ")"
        )
        labelcolors_iTOL.append(color_i)
    dfCellColor = pd.DataFrame()
    dfCellColor["cellBC"] = _leaves
    dfCellColor["color"] = labelcolors_iTOL

    # save file with header
    header = [
        "DATASET_COLORSTRIP",
        "SEPARATOR TAB",
        "COLOR\t#FF0000",
        "MARGIN\t100",
        f"DATASET_LABEL\t{dataset_name}",
        "STRIP_WIDTH\t100",
        "SHOW_INTERNAL\t0",
        "",
    ]

    outfp = os.path.join(output_directory, f"{dataset_name}.txt")
    with open(outfp, "w") as SIDout:
        for line in header:
            SIDout.write(line + "\n")

        if create_legend:
            number_of_items = len(colormap)

            SIDout.write(f"LEGEND_TITLE\t{dataset_name} legend\n")
            SIDout.write("LEGEND_SHAPES")
            for _ in range(number_of_items):
                SIDout.write("\t1")

            SIDout.write("\nLEGEND_COLORS")
            for col in colormap.values():
                SIDout.write(f"\t{rgb_to_hex(col)}")

            SIDout.write("\nLEGEND_LABELS")
            for key in colormap.keys():
                SIDout.write(f"\t{key}")
            SIDout.write("\n")

        SIDout.write("\nDATA\n")
        df_writeout = dfCellColor.to_csv(
            None, sep="\t", header=False, index=False
        )
        SIDout.write(df_writeout)

    return outfp


def create_indel_heatmap(
    alleletable: pd.DataFrame,
    cassiopeia_tree: CassiopeiaTree,
    dataset_name: str,
    output_directory: str,
    indel_colors: Optional[pd.DataFrame] = None,
    indel_priors: Optional[pd.DataFrame] = None,
) -> Tuple[pd.DataFrame, pd.DataFrame]:

    _leaves = tree.leaves

    lineage_profile = utilities.convert_alleletable_to_lineage_profile(
        alleletable
    )
    clustered_linprof = lineage_profile.loc[_leaves[::-1]]

    if indel_colors is None:
        if indel_priors is None:
            indel_colors = get_random_indel_colors(lineage_profile)
        else:
            indel_colors = get_indel_colors(indel_priors)

    # Convert colors and make colored alleleTable (rgb_heatmap)
    r, g, b = (
        np.zeros(clustered_linprof.shape),
        np.zeros(clustered_linprof.shape),
        np.zeros(clustered_linprof.shape),
    )
    for i in tqdm(range(clustered_linprof.shape[0])):
        for j in range(clustered_linprof.shape[1]):
            ind = str(clustered_linprof.iloc[i, j])
            if ind == "nan":
                r[i, j], g[i, j], b[i, j] = 1, 1, 1
            elif "None" in ind:
                r[i, j], g[i, j], b[i, j] = 192 / 255, 192 / 255, 192 / 255
            else:
                col = hsv_to_rgb(tuple(indel_colors.loc[ind, "colors"]))
                r[i, j], g[i, j], b[i, j] = col[0], col[1], col[2]

    rgb_heatmap = np.stack((r, g, b), axis=2)

    alfiles = []
    for j in range(0, rgb_heatmap.shape[1]):
        item_list = []
        for i in rgb_heatmap[:, j]:
            item = (
                "rgb("
                + str(int(round(255 * i[0])))
                + ","
                + str(int(round(255 * i[1])))
                + ","
                + str(int(round(255 * i[2])))
                + ")"
            )
            item_list.append(item)
        dfAlleleColor = pd.DataFrame()
        dfAlleleColor["cellBC"] = clustered_linprof.index.values
        dfAlleleColor["color"] = item_list

        if j == 0:
            header = [
                "DATASET_COLORSTRIP",
                "SEPARATOR TAB",
                "COLOR\t#000000",
                "MARGIN\t100",
                "DATASET_LABEL\tallele" + str(j),
                "STRIP_WIDTH\t50",
                "SHOW_INTERNAL\t0",
                "DATA",
                "",
            ]
        else:
            header = [
                "DATASET_COLORSTRIP",
                "SEPARATOR TAB",
                "COLOR\t#000000",
                "DATASET_LABEL\tallele" + str(j),
                "STRIP_WIDTH\t50",
                "SHOW_INTERNAL\t0",
                "DATA",
                "",
            ]

        if len(str(j)) == 1:
            alleleLabel_fileout = os.path.join(output_directory, f"indelColors_0{j}.txt")
        elif len(str(j)) == 2:
            alleleLabel_fileout = os.path.join(output_directory, f"indelColors_{j}.txt")
        with open(alleleLabel_fileout, "w") as ALout:
            for line in header:
                ALout.write(line + "\n")
            df_writeout = dfAlleleColor.to_csv(
                None, sep="\t", header=False, index=False
            )
            ALout.write(df_writeout)

        alfiles.append(alleleLabel_fileout)

    return alfiles, rgb_heatmap


def get_random_indel_colors(lineage_profile: pd.DataFrame) -> pd.DataFrame:
    """Assigns random color to each unique indel.

    Assigns a random HSV value to each indel observed in the specified
    lineage profile.

    Args:
        lineage_profile: An NxM lineage profile reporting the indels observed
            at each cut site in a cell.

    Returns:
        A mapping from indel to HSV color.
    """

    unique_indels = np.unique(
        lineage_profile.apply(lambda x: x.unique(), axis=0)
    )

    # color families
    redmag = [0.5, 1, 0, 0.5, 0, 1]
    grnyel = [0, 1, 0.5, 1, 0, 0.5]
    cynblu = [0, 0.5, 0, 1, 0.5, 1]
    colorlist = [redmag, grnyel, cynblu]

    # construct dictionary of indels-to-RGBcolors
    indel2color = {}
    for indel in unique_indels:
        if "none" in indel.lower():
            indel2color[indel] = rgb_to_hsv((0.75, 0.75, 0.75))
        if indel == "NC":
            indel2color[indel] = rgb_to_hsv((0, 0, 0))
        else:
            rgb_i = np.random.choice(
                range(len(colorlist))
            )  # randomly pick a color family
            indel2color[indel] = rgb_to_hsv(
                random_color(colorlist[rgb_i])
            )  # pick random color within color family

    return pd.DataFrame.from_dict(
        indel2color, orient="index", columns=["color"]
    )


def get_indel_colors(indel_priors: pd.DataFrame):
    """Map indel to HSV colors using prior probabilities.

    Given prior probabilities of indels, map each indel to a color reflecting
    its relative likelihood. Specifically, indels that are quite frequent will
    have dull colors and indels that are rare will be bright.

    Args:
        indel_priors: DataFrame mapping indels to probabilities

    Returns:
        DataFrame mapping indel to color
    """

    def assign_color(prob):
        H = np.random.rand()
        S = prob
        V = 0.5 + 0.5 * S
        return (H, S, V)

    indel_priors_copy = indel_priors
    indel_priors_copy["NormFreq"] = indel_priors_copy["freq"]
    indel_priors_copy["NormFreq"] = indel_priors_copy.apply(
        lambda x: (indel_priors_copy["NormFreq"].max() - x.NormFreq), axis=1
    )
    indel_priors_copy["NormFreq"] /= indel_priors_copy["NormFreq"].max()
    indels_priors_copy["color"] = indels.apply(
        lambda x: assign_color(x.NormFreq), axis=1
    )
    return indels_priors_copy["color"]


def hex_to_rgb(value) -> Tuple[int, int, int]:
    """Converts Hex color code to RGB.

    Args:
        values: hex values (beginning with "#")
    
    Returns:
        A tuple denoting (r, g, b) 
    """
    value = value.lstrip("#")
    lv = len(value)
    return tuple(int(value[i : i + lv // 3], 16) for i in range(0, lv, lv // 3))


def random_color(rgb):
    """Generates a random color"""

    red = np.random.uniform(rgb[0], rgb[1])
    grn = np.random.uniform(rgb[2], rgb[3])
    blu = np.random.uniform(rgb[4], rgb[5])
    return (red, grn, blu)

"""
This file stores a subclass of CassiopeiaSolver, the DistanceSolver. Generally,
the inference procedures that inherit from this method will need to implement
methods for selecting "cherries" and updating the dissimilarity map. Methods
that will inherit from this class by default are Neighbor-Joining and UPGMA.
There may be other subclasses of this.
"""
import abc
import networkx as nx
import numba
import numpy as np
import pandas as pd
import scipy
from typing import Callable, Dict, List, Optional, Tuple

from cassiopeia.data import CassiopeiaTree
from cassiopeia.solver import CassiopeiaSolver, solver_utilities


class DistanceSolverError(Exception):
    """An Exception class for all DistanceSolver subclasses."""

    pass


class DistanceSolver(CassiopeiaSolver.CassiopeiaSolver):
    """Distance based solver class

    This solver serves as a generic Distance-based solver. Briefly, all of the
    classes that derive from this class will use a dissimilarity map to 
    iteratively choose samples to merge and update the dissimilarity map
    based on this merging. An example of a derived class is the
    NeighborJoiningSolver which uses the Q-criterion to iteratively join
    samples until no samples remain.

    TODO(mgjones, sprillo): Specify functions to use for rooting, etc. the
        trees that are produced via a DistanceSolver.

    Args:
        dissimilarity_function: Function that can be used to compute the
            dissimilarity between samples.
        add_root: Whether or not to root the tree. Only pertinent in algorithms
            that return an unrooted tree, by default (e.g. Neighbor Joining)
        prior_transformation: Function to use when transforming priors into
            weights. Supports the following transformations:
                "negative_log": Transforms each probability by the negative
                    log (default)
                "inverse": Transforms each probability p by taking 1/p
                "square_root_inverse": Transforms each probability by the
                    the square root of 1/p
    """

    def __init__(
        self,
        dissimilarity_function: Optional[
            Callable[
                [np.array, np.array, int, Dict[int, Dict[int, float]]], float
            ]
        ] = None,
        add_root: bool = False,
        prior_transformation: str = "negative_log",
    ):

        super().__init__(prior_transformation)

        self.dissimilarity_function = dissimilarity_function
        self.add_root = add_root


    def solve(self, cassiopeia_tree: CassiopeiaTree) -> None:
        """A general bottom-up distance-based solver routine.

        The general solver routine proceeds by iteratively finding pairs of
        samples to join together into a "cherry" and then reform the
        dissimilarity matrix with respect to this new cherry. The implementation
        of how to find cherries and update the dissimilarity map is left to
        subclasses of DistanceSolver. The function will update the `tree`
        attribute of the input CassiopeiaTree.

        Args:
            cassiopeia_tree: CassiopeiaTree object to be populated
        """

        self.setup_dissimilarity_map(cassiopeia_tree)

        dissimilarity_map = cassiopeia_tree.get_dissimilarity_map()

        N = dissimilarity_map.shape[0]

        identifier_to_sample = dict(
            zip([str(i) for i in range(N)], dissimilarity_map.index)
        )

        # instantiate a dissimilarity map that can be updated as we join
        # together nodes.
        _dissimilarity_map = dissimilarity_map.copy()

        # instantiate a tree where all samples appear as leaves.
        tree = nx.Graph()
        tree.add_nodes_from(dissimilarity_map.index)

        while N > 2:

            i, j = self.find_cherry(_dissimilarity_map.to_numpy())

            # get indices in the dissimilarity matrix to join
            node_i, node_j = (
                _dissimilarity_map.index[i],
                _dissimilarity_map.index[j],
            )

            new_node_name = str(len(tree.nodes))
            tree.add_node(new_node_name)
            tree.add_edges_from(
                [(new_node_name, node_i), (new_node_name, node_j)]
            )

            _dissimilarity_map = self.update_dissimilarity_map(
                _dissimilarity_map, (node_i, node_j), new_node_name
            )

            N = _dissimilarity_map.shape[0]

        remaining_samples = _dissimilarity_map.index.values
        tree.add_edge(remaining_samples[0], remaining_samples[1])

        tree = nx.relabel_nodes(tree, identifier_to_sample)

        if cassiopeia_tree.root_sample_name is not None:
            tree = self.root_tree(tree, cassiopeia_tree.root_sample_name)

        cassiopeia_tree.populate_tree(tree)

    def setup_dissimilarity_map(
        self, cassiopeia_tree: CassiopeiaTree
    ) -> Tuple[pd.DataFrame, pd.DataFrame, Dict[str, List[str]], str]:
        """Sets up the solver.

        Sets up the solver with respect to the input CassiopeiaTree by
        extracting the character matrix, creating the dissimilarity map if
        needed, and setting up the "root" sample if the tree will be rooted.

        Args:
            cassiopeia_tree: Input CassiopeiaTree to `solve`.

        Returns:
            A character matrix with duplicate rows filtered out, a
                dissimilarity map, a mapping from state to sample name, and
                the sample to treat as a root.
        """

        character_matrix = (
            cassiopeia_tree.get_current_character_matrix().copy()
        )

        # if root sample is not specified, we'll add the implicit root
        # and recompute the dissimilarity map

        if cassiopeia_tree.root_sample_name is None and self.add_root:
            root = [0] * character_matrix.shape[1]
            character_matrix.loc["root"] = root
            cassiopeia_tree.root_sample_name = "root"
            cassiopeia_tree.set_character_matrix(character_matrix)

            if self.dissimilarity_function is None:
                raise DistanceSolverError(
                    "Please specify a dissimilarity function to add an implicit "
                    "root, or specify an explicit root"
                )

            cassiopeia_tree.compute_dissimilarity_map(
                self.dissimilarity_function, self.prior_transformation
            )

        if cassiopeia_tree.get_dissimilarity_map() is None:
            if self.dissimilarity_function is None:
                raise DistanceSolverError(
                    "Please specify a dissimilarity function or populate the "
                    "CassiopeiaTree object with a dissimilarity map"
                )

            cassiopeia_tree.compute_dissimilarity_map(
                self.dissimilarity_function, self.prior_transformation
            )


    @abc.abstractmethod
    def root_tree(self, tree, root_sample):
        """Roots a tree.

        Finds a location on the tree to place a root and converts the general
        graph to a directed graph with respect to that root.
        """
        pass

    @abc.abstractmethod
    def find_cherry(
        self, dissimilarity_map: np.array(float)
    ) -> Tuple[int, int]:
        """Selects two samples to join together as a cherry.

        Selects two samples from the dissimilarity map to join together as a
        cherry in the forming tree.

        Args:
            dissimilarity_map: A dissimilarity map relating samples

        Returns:
            A tuple of samples to join together.
        """
        pass

    @abc.abstractmethod
    def update_dissimilarity_map(
        self,
        dissimilarity_map: pd.DataFrame,
        cherry: Tuple[str, str],
        new_node: str
    ) -> pd.DataFrame:
        """Updates dissimilarity map with respect to new cherry.

        Args:
            dissimilarity_map: Dissimilarity map to update
            cherry1: One of the children to join.
            cherry2: One of the children to join.
            new_node: New node name to add to the dissimilarity map

        Returns:
            An updated dissimilarity map.
        """
        pass

    def __append_sample_names(
        self,
        solution: nx.DiGraph,
        state_to_sample_mapping: Dict[str, List[str]],
    ) -> nx.DiGraph:
        """Append sample names to character states in tree.

        Given a tree where every node corresponds to a set of character states,
        append sample names at the deepest node that has its character
        state. The DistanceSolver by default has observed samples as leaves,
        so this procedure is simply to stitch samples names onto the leaves
        at the appropriate location.

        Args:
            solution: A DistanceSolver solution that we wish to add sample
                names to.
            state_to_sample_mapping: A dictionary mapping a state to a set
                 of samples

        Returns:
            A solution with extra leaves corresponding to sample names.
        """

        leaves = [n for n in solution if solution.degree(n) == 1]

        for l in leaves:

            if l not in state_to_sample_mapping.keys():
                continue

            # remove samples with the same name as the leaf
            samples = [s for s in state_to_sample_mapping[l] if s != l]

            if len(samples) > 0:
                solution.add_edges_from([(l, sample) for sample in samples])

        return solution

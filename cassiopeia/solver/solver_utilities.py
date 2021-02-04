"""This file contains general utilities to be called by functions throughout 
the solver module"""

import logging

import ete3
import numpy as np
import pandas as pd
import networkx as nx

from collections import defaultdict
from typing import Callable, Dict, List, Optional, Tuple, Union
from cassiopeia.data import utilities as data_utilities


class InferAncestorError(Exception):
    """An Exception class for collapsing edges, indicating a necessary argument
    was not included.
    """

    pass

def annotate_ancestral_characters(
    T: nx.DiGraph,
    node: Union[int, str],
    node_to_characters: Dict[Union[int, str], List[int]],
    missing_char: int,
):
    """Annotates the character vectors of the internal nodes of a reconstructed
    network from the samples, obeying Camin-Sokal Parsimony.

    For an internal node, annotates that node's character vector to be the LCA
    of its daughter character vectors. Annotates from the samples upwards.

    Args:
        T: A networkx DiGraph object representing the tree
        node: The node whose state is to be inferred
        node_to_characters: A dictionary that maps nodes to their character vectors
        missing_char: The character representing missing values

    Returns:
        None, annotates node_to_characters dictionary with node/character vector pairs


    """
    if T.out_degree(node) == 0:
        return
    vecs = []
    for i in T.successors(node):
        annotate_ancestral_characters(T, i, node_to_characters, missing_char)
        vecs.append(node_to_characters[i])
    lca_characters = data_utilities.get_lca_characters(vecs, missing_char)
    node_to_characters[node] = lca_characters
    T.nodes[node]["characters"] = lca_characters

def collapse_edges(
    T: nx.DiGraph,
    node: Union[int, str],
    node_to_characters: Dict[Union[int, str], List[int]],
):
    """A helper function to collapse mutationless edges in a tree in-place.

    Collapses an edge if the character vector of the parent node is identical
    to its daughter, removing the identical daughter and creating edges between
    the parent and the daughter's children. Does not collapse at the level of
    the samples. Can create multifurcating trees from strictly binary trees.

    Args:
        T: A networkx DiGraph object representing the tree
        node: The node whose state is to be inferred
        node_to_characters: A dictionary that maps nodes to their character vectors

    Returns:
        None, operates on the tree destructively
    """
    if T.out_degree(node) == 0:
        return
    to_remove = []
    to_collapse = []
    for i in T.successors(node):
        to_collapse.append(i)
    for i in to_collapse:
        if T.out_degree(i) > 0:
            collapse_edges(T, i, node_to_characters)
            if node_to_characters[i] == node_to_characters[node]:
                for j in T.successors(i):
                    T.add_edge(node, j)
                to_remove.append(i)
    for i in to_remove:
        T.remove_node(i)


def collapse_tree(
    tree: nx.DiGraph,
    infer_ancestral_characters: bool,
    character_matrix: Optional[pd.DataFrame] = None,
    missing_char: Optional[int] = None,
):
    """Collapses mutationless edges in a tree in-place.

    Uses the internal node annotations of a tree to collapse edges with no
    mutations. Either takes in a tree with internal node annotations or
    a tree without annotations and infers the annotations bottom-up from the
    samples obeying Camin-Sokal Parsimony. If ground truth internal annotations
    exist, it is suggested that they are used directly and that the annotations
    are not inferred again using the parsimony method.

    Args:
        tree: A networkx DiGraph object representing the tree
        infer_ancestral_characters: Infer the ancestral characters states of
            the tree
        character_matrix: A character matrix storing character states for each
            leaf
        missing_char: Character state indicating missing data

    Returns:
        A collapsed tree

    """
    leaves = [
        n for n in tree if tree.out_degree(n) == 0 and tree.in_degree(n) == 1
    ]
    root = [n for n in tree if tree.in_degree(n) == 0][0]
    node_to_characters = {}

    # Populates the internal annotations using either the ground truth
    # annotations, or infers them
    if infer_ancestral_characters:
        if character_matrix is None or missing_char is None:
            logging.info(
                "In order to infer ancestral characters, a character matrix and missing character are needed"
            )
            raise InferAncestorError()

        for i in leaves:
            node_to_characters[i] = list(character_matrix.loc[i, :])
            tree.nodes[i]["characters"] = list(character_matrix.loc[i, :])
        annotate_ancestral_characters(
            tree, root, node_to_characters, missing_char
        )
    else:
        for i in tree.nodes():
            node_to_characters[i] = tree.nodes[i]["characters"]

    # Calls helper function on root, passing in the mapping dictionary
    collapse_edges(tree, root, node_to_characters)
    return tree


def collapse_unifurcations(tree: ete3.Tree) -> ete3.Tree:
    """Collapse unifurcations.

    Collapse all unifurcations in the tree, namely any node with only one child
    should be removed and all children should be connected to the parent node.

    Args:
        tree: tree to be collapsed

    Returns:
        A collapsed tree.
    """

    collapse_fn = lambda x: (len(x.children) == 1)

    collapsed_tree = tree.copy()
    to_collapse = [n for n in collapsed_tree.traverse() if collapse_fn(n)]

    for n in to_collapse:
        n.delete()

    return collapsed_tree


def transform_priors(
    priors: Optional[Dict[int, Dict[int, float]]] = None,
    prior_function: Optional[Callable[[float], float]] = None,
):
    """Generates a dictionary of negative log probabilities from priors.

    Generates a dicitonary of weights for use in algorithms that inheret the
    GreedySolver from given priors.

    Args:
        priors: A dictionary of prior probabilities for each character/state
            pair
        prior_function: A function defining a transformation on the priors
            in forming weights

    Returns:
        A dictionary of weights for each character/state pair
    """
    weights = {}
    for character in priors:
        state_weights = {}
        for state in priors[character]:
            state_weights[state] = prior_function(priors[character][state])
        weights[character] = state_weights
    return weights

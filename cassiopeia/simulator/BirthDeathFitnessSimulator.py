"""
A general simulator for a birth-death tree simulation process, including 
fitness. Takes any given distribution on waiting times and fitness 
mutations.
"""

import networkx as nx
import numpy as np

from typing import Callable

from cassiopeia.data.CassiopeiaTree import CassiopeiaTree
from cassiopeia.simulator import TreeSimulator


class BirthDeathFitnessError(Exception):
    """An Exception class for all exceptions generated by the
    GeneralBirthDeathSimulator
    """

    pass


class BirthDeathFitnessSimulator(TreeSimulator):
    def simulate_tree(
        self,
        birth_waiting_dist: Callable[[float], float],
        birth_scale_param: float,
        death_waiting_dist: Callable[[], float] = None,
        fitness_num_dist: Callable[[], int] = None,
        fitness_strength_dist: Callable[[], float] = None,
        num_extant: int = None,
        experiment_time: float = None,
    ) -> CassiopeiaTree:
        """Simulates trees from a general birth/death process with fitness.

        The birth/death process is simulated by maintaining a list of living
        lineages and updating them with birth and death events. At each
        currently extant node in the tree, two events are sampled for two
        children. For each sampled event, waiting times are sampled from the
        birth and death distributions, and the smaller time is used to
        represent the next event. If a death event is sampled, no child is
        added to the tree and the lineage is no longer updated. If a birth
        event is sampled, then a new internal node representing a division
        event is added, with the edge weight representing how long this node
        lived before dividing. The total time the lineage has existed is also
        record for each lineage. If no death waiting time distribution is
        provided, the process reduces to a Yule birth process.

        Fitness is represented by each lineage mainting its own birth scale
        parameter. This parameter determines the shape of the distribution
        from which birth waiting times are sampled and thus affects how
        quickly cells divide. At each division event, the fitness is updated
        by sampling from a distribution determining the number of mutations,
        and the multiplicative strength of each mutation is determined by
        another distribution. The birth scale parameter of the lineage is
        then updated by the total multiplicative strength factor across all
        mutations and passed on to the child nodes.

        There are two stopping conditions for the simulation. The first is
        "number of extant nodes", which specifies the simulation to stop the
        first moment the specified number of extant nodes exist. The second is
        "experiment time", which specifies the time at which to end the
        experiment, i.e. the experiment ends when all living lineages reach
        this time in their total lived time.

        Args:
            birth_waiting_dist: A function that samples waiting times from the
                birth distribution. Must take a scale parameter as the input
            birth_scale_param: The global scale parameter that is used at the
                start of the experiment
            death_waiting_dist: A function that samples waiting times from the
                death distribution
            fitness_num_dist: A function that samples the number of mutations
                that occurs at a division event
            fitness_strength_dist: A function that samples the multiplicative
                update to the scale parameter of the current lineage at a
                division event
            num_extant: Specifies the number of extant lineages living at one
                time as a stopping condition for the experiment
            experiment_time: Specifies the time that the experiment runs as a
                stopping condition for the experiment

        Returns:
            A CassiopeiaTree with the 'tree' field populated
        """
        if num_extant is None and experiment_time is None:
            raise BirthDeathFitnessError("Please specify a stopping condition")
        if num_extant and experiment_time:
            raise BirthDeathFitnessError(
                "Please choose only one stopping condition"
            )
        if fitness_num_dist is not None and fitness_strength_dist is None:
            raise BirthDeathFitnessError(
                "Please specify a fitness strength distribution"
            )
        if num_extant is not None and num_extant <= 0:
            raise BirthDeathFitnessError(
                "Please specify number of extant lineages greater than 0"
            )
        if experiment_time is not None and experiment_time <= 0:
            raise BirthDeathFitnessError(
                "Please specify an experiment time greater than 0"
            )

        if death_waiting_dist is None:
            death_waiting_dist = lambda: np.inf

        # Samples whether birth, death, or the end of the experiment comes next
        # for a given lineage, and any fitness changes
        def sample_event(unique_id, lineage):
            birth_waiting_time = birth_waiting_dist(lineage["birth_scale"])
            death_waiting_time = death_waiting_dist()
            if birth_waiting_time <= 0 or death_waiting_time <= 0:
                raise BirthDeathFitnessError(
                    "0 or negative waiting time detected"
                )

            # If birth or death would happen after the total experiment time,
            # just cut off the living branch length at the experiment time
            if (
                experiment_time
                and lineage["total_time"] + birth_waiting_time
                >= experiment_time
                and lineage["total_time"] + death_waiting_time
                >= experiment_time
            ):
                tree.add_node(unique_id)
                tree.nodes[unique_id]["birth_scale"] = lineage["birth_scale"]
                tree.add_edge(
                    lineage["id"],
                    unique_id,
                    weight=experiment_time - lineage["total_time"],
                )
                tree.nodes[unique_id]["total_time"] = experiment_time
                return unique_id + 1

            if birth_waiting_time < death_waiting_time:
                # Update fitness
                total_birth_mutation_strength = 1
                if fitness_num_dist:
                    num_mutations = int(fitness_num_dist())
                    if num_mutations < 0:
                        raise BirthDeathFitnessError(
                            "Negative number of mutations detected"
                        )
                    for _ in range(num_mutations):
                        total_birth_mutation_strength *= fitness_strength_dist()
                    if total_birth_mutation_strength < 0:
                        raise BirthDeathFitnessError(
                            "Negative mutation strength detected"
                        )

                # Annotate parameters for a given node in the tree
                tree.add_node(unique_id)
                tree.nodes[unique_id]["birth_scale"] = (
                    lineage["birth_scale"] * total_birth_mutation_strength
                )
                tree.add_edge(
                    lineage["id"], unique_id, weight=birth_waiting_time
                )
                tree.nodes[unique_id]["total_time"] = (
                    birth_waiting_time + lineage["total_time"]
                )
                # Add the newly generated cell to the list of living lineages
                current_lineages.append(
                    {
                        "id": unique_id,
                        "birth_scale": lineage["birth_scale"]
                        * total_birth_mutation_strength,
                        "total_time": birth_waiting_time
                        + lineage["total_time"],
                    }
                )
                return unique_id + 1
            else:
                return unique_id

        # Instantiate the implicit root
        tree = nx.DiGraph()
        tree.add_node(0)
        tree.nodes[0]["birth_scale"] = birth_scale_param
        tree.nodes[0]["total_time"] = 0
        current_lineages = []
        starting_lineage = {
            "id": 0,
            "birth_scale": birth_scale_param,
            "total_time": 0,
        }

        # Sample the waiting time until the first division
        unique_id = 1
        unique_id = sample_event(unique_id, starting_lineage)

        # Perform the process until there are no active extant lineages left
        while len(current_lineages) > 0:
            # If number of extant lineages is the stopping criterion, at the
            # first instance of having n extant tips, stop the experiment
            # and set the total lineage time for each lineage to be equal to
            # the minimum, to produce ultrametric trees. Also, the birth_scale
            # parameter of each leaf is rolled back to equal its parent's.
            if num_extant:
                if len(current_lineages) == num_extant:
                    min_total_time = min(
                        [i["total_time"] for i in current_lineages]
                    )
                    for remaining_lineage in current_lineages:
                        parent = list(
                            tree.predecessors(remaining_lineage["id"])
                        )[0]
                        tree.edges[parent, remaining_lineage["id"]][
                            "weight"
                        ] += (min_total_time - remaining_lineage["total_time"])
                        tree.nodes[remaining_lineage["id"]][
                            "birth_scale"
                        ] = tree.nodes[parent]["birth_scale"]
                    break
            # If extant tips are the stopping criteria, pop the minimum age
            # lineage at each step
            if num_extant:
                min_age_ind = np.argmin(
                    [i["total_time"] for i in current_lineages]
                )
                lineage = current_lineages.pop(min_age_ind)
            else:
                lineage = current_lineages.pop(0)
            for _ in range(2):
                unique_id = sample_event(unique_id, lineage)

        # Prune dead lineages and collapse resulting unifurcations
        if death_waiting_dist and len(tree.nodes) > 1:
            if experiment_time:
                for i in list(tree.nodes):
                    if (
                        tree.out_degree(i) == 0
                        and tree.nodes[i]["total_time"] < experiment_time
                    ):
                        self.remove_and_prune_lineage(i, tree)
            if num_extant:
                surviving_ids = [i["id"] for i in current_lineages]
                for i in list(tree.nodes):
                    if tree.out_degree(i) == 0 and i not in surviving_ids:
                        self.remove_and_prune_lineage(i, tree)
            if len(tree.nodes) > 1:
                self.collapse_unifurcations(tree, source=1)

        # If only implicit root remains after pruning dead lineages, error
        if len(tree.nodes) == 1:
            raise BirthDeathFitnessError(
                "All lineages died before stopping condition"
            )

        return CassiopeiaTree(tree=tree)

    def remove_and_prune_lineage(self, node: int, tree: nx.DiGraph):
        """Removes a node and prunes the lineage.

        Removes a node and all ancestors of that node that are no longer the
        ancestor of any leaves. In the context of a lineage tracing
        experiment, this removes all ancestral nodes that are not the
        ancestors of any observed samples at the end of the experiment, thus
        pruning all lineages that died.

        Args:
            node: The node to be removed
            tree: The tree to remove the node from
        """
        if len(tree.nodes) > 1:
            curr_parent = list(tree.predecessors(node))[0]
            tree.remove_node(node)
            while (
                tree.out_degree(curr_parent) < 1
                and tree.in_degree(curr_parent) > 0
            ):
                next_parent = list(tree.predecessors(curr_parent))[0]
                tree.remove_node(curr_parent)
                curr_parent = next_parent

    def collapse_unifurcations(
        self, tree: nx.DiGraph, source: int = None
    ) -> None:
        """Collapses unifurcations in a given tree.

        Args:
            tree: The tree to collapse unifurcations on
            source: The node at which to begin the tree traversal
        """

        def _collapse_unifurcations(tree, node, parent):
            succs = list(tree.successors(node))
            if len(succs) == 1:
                t = tree.get_edge_data(parent, node)["weight"]
                t_ = tree.get_edge_data(node, succs[0])["weight"]
                tree.add_edge(parent, succs[0], weight=t + t_)
                _collapse_unifurcations(tree, succs[0], parent)
                tree.remove_node(node)
            else:
                for i in succs:
                    _collapse_unifurcations(tree, i, node)

        if not source:
            source = [n for n in tree if tree.in_degree(n) == 0][0]

        for node in tree.successors(source):
            _collapse_unifurcations(tree, node, source)

        succs = list(tree.successors(source))
        if len(succs) == 1:
            t = tree.get_edge_data(source, succs[0])["weight"]
            for i in tree.successors(succs[0]):
                t_ = tree.get_edge_data(succs[0], i)["weight"]
                tree.add_edge(source, i, weight=t + t_)
            tree.remove_node(succs[0])


"""Example use snippet:
note that numpy uses a different parameterization of the exponential with the scale parameter, which is 1/rate


birth_waiting_dist = np.random.exponential
death_waiting_dist = np.random.exponential(1.5)
birth_scale_param = 0.5
fitness_num_dist = lambda: 1 if np.random.uniform() > 0.5 else 0
fitness_strength_dist = lambda: 2 ** np.random.uniform(-1,1)

tree = generate_birth_death(
    birth_waiting_dist,
    birth_scale_param,
    death_waiting_dist,
    fitness_num_dist = fitness_num_dist,
    fitness_strength_dist=fitness_strength_dist,
    num_extant=8,
#     experiment_time = 1
)

"""

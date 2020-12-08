"""
Common code for the pyslim test cases.
"""
from __future__ import print_function
from __future__ import unicode_literals
from __future__ import division

import pyslim
import tskit
import msprime
import random
import unittest
import pytest
import base64
import os
import attr
import json
import numpy as np

# possible attributes to simulation scripts are
#  WF, nonWF
#  nucleotides
#  everyone: records everyone ever
#  pedigree: writes out accompanying info file containing the pedigree
#  remembered_early: remembering and saving the ts happens during early
#  multipop: has more than one population
# All files are of the form `tests/examples/{key}.slim`
example_files = {}
example_files['recipe_nonWF'] = {"nonWF": True, "pedigree": True}
example_files['recipe_long_nonWF'] = {"nonWF": True}
example_files['recipe_WF'] = {"WF": True, "pedigree": True}
example_files['recipe_long_WF'] = {"WF": True}
example_files['recipe_WF_migration'] = {"WF": True, "pedigree": True, "multipop": True}
example_files['recipe_nonWF_early'] = {"nonWF": True, "pedigree": True, "remembered_early": True}
example_files['recipe_WF_early'] = {"WF": True, "pedigree": True, "remembered_early": True}
example_files['recipe_nucleotides'] = {"WF": True, "pedigree": True, "nucleotides": True}
example_files['recipe_long_nucleotides'] = {"WF": True, "nucleotides": True}
example_files['recipe_roots'] = {"WF": True, "pedigree": True}
example_files['recipe_nonWF_selfing'] = {"nonWF": True, "pedigree": True}
example_files['recipe_init_mutated_WF'] = {"WF": True, "init_mutated": True}
example_files['recipe_init_mutated_nonWF'] = {"nonWF": True, "init_mutated": True}
for t in ("WF", "nonWF"):
    for s in ("early", "late"):
        value = {t: True, "everyone": True, "pedigree": True}
        if s == 'early':
            value['remembered_early'] = True
        example_files[f'recipe_record_everyone_{t}_{s}'] = value


for f in example_files:
    example_files[f]['basename'] = os.path.join("tests", "examples", f)


# These SLiM scripts read in an existing trees file; the "input" gives a .trees files produced
# by recipes above that is appropriate for starting this script.
restart_files = {}
for t in ("WF", "nonWF"):
    # recipes that read in and write out immediately ("no_op")
    value = {t: True, "no_op": True, "input": f"tests/examples/recipe_{t}.trees"}
    restart_files[f'restart_{t}'] = value
restart_files['restart_nucleotides'] = {"WF": True, "nucleotides": True, "no_op": True, "input": f"tests/examples/recipe_nucleotides.trees"}
restart_files['restart_and_run_WF'] = {"WF": True, "input": "recipe_init_mutated.trees"}
restart_files['restart_and_run_nonWF'] = {"nonWF": True, "input": "recipe_init_mutated.trees"}

for f in restart_files:
    restart_files[f]['basename'] = os.path.join("tests", "examples", f)


def run_slim_script(slimfile, seed=23, **kwargs):
    outdir = os.path.dirname(slimfile)
    script = os.path.basename(slimfile)
    args = f"-s {seed}"
    for k in kwargs:
        x = kwargs[k]
        if x is not None:
            if isinstance(x, str):
                x = f"'{x}'"
            if isinstance(x, bool):
                x = 'T' if x else 'F'
            args += f" -d \"{k}={x}\""
    command = "cd \"" + outdir + "\" && slim " + args + " \"" + script + "\" >/dev/null"
    print("running: ", command)
    out = os.system(command)
    return out


class PyslimTestCase:
    '''
    Base class for test cases in pyslim.
    '''

    def verify_haplotype_equality(self, ts, slim_ts):
        assert ts.num_sites == slim_ts.num_sites
        for j, v1, v2 in zip(range(ts.num_sites), ts.variants(),
                             slim_ts.variants()):
            g1 = [v1.alleles[x] for x in v1.genotypes]
            g2 = [v2.alleles[x] for x in v2.genotypes]
            assert np.array_equal(g1, g2)

    def get_slim_example(self, name, return_info=False):
        ex = example_files[name]
        treefile = ex['basename'] + ".trees"
        print("---->", treefile)
        assert os.path.isfile(treefile)
        ts = pyslim.load(treefile)
        if return_info:
            infofile = treefile + ".pedigree"
            if os.path.isfile(infofile):
                ex['info'] = self.get_slim_info(infofile)
            else:
                ex['info'] = None
            out = (ts, ex)
        else:
            out = ts
        return out

    def get_slim_examples(self, return_info=False, **kwargs):
        num_examples = 0
        for name, ex in example_files.items():
            use = True
            for a in kwargs:
                if a in ex:
                    if ex[a] != kwargs[a]:
                        use = False
                else:
                    if kwargs[a] != False:
                        use = False
            if use:
                num_examples += 1
                yield self.get_slim_example(name, return_info=return_info)
        assert num_examples > 0

    def get_slim_restarts(self, **kwargs):
        # Loads previously produced tree sequences and SLiM scripts
        # appropriate for restarting from these tree sequences.
        for exname in restart_files:
            ex = restart_files[exname]
            use = True
            for a in kwargs:
                if a not in ex or ex[a] != kwargs[a]:
                    use = False
            if use:
                basename = ex['basename']
                treefile = ex['input']
                print(f"restarting {treefile} as {basename}")
                assert os.path.isfile(treefile)
                ts = pyslim.load(treefile)
                yield ts, basename

    def run_slim_restart(self, in_ts, basename, **kwargs):
        # Saves out the tree sequence to the trees file that the SLiM script
        # basename.slim will load from.
        infile = basename + ".init.trees"
        outfile = basename + ".trees"
        slimfile = basename + ".slim"
        for treefile in infile, outfile:
            try:
                os.remove(treefile)
            except FileNotFoundError:
                pass
        in_ts.dump(infile)
        if 'STAGE' not in kwargs:
            kwargs['STAGE'] = in_ts.metadata['SLiM']['stage']
        out = run_slim_script(slimfile, **kwargs)
        try:
            os.remove(infile)
        except FileNotFoundError:
            pass
        assert out == 0
        assert os.path.isfile(outfile)
        out_ts = pyslim.load(outfile)
        try:
            os.remove(outfile)
        except FileNotFoundError:
            pass
        return out_ts

    def run_msprime_restart(self, in_ts, sex=None, WF=False):
        basename = "tests/examples/restart_msprime"
        out_ts = self.run_slim_restart(
                    in_ts, basename, WF=WF, SEX=sex, L=int(in_ts.sequence_length))
        return out_ts

    def get_msprime_examples(self):
        # NOTE: we use DTWF below to avoid rounding of floating-point times
        # that occur with a continuous-time simulator
        demographic_events = [
            msprime.MassMigration(
            time=5, source=1, destination=0, proportion=1.0)
        ]
        seed = 6
        for n in [2, 10, 20]:
            for mutrate in [0.0]:
                for recrate in [0.0, 0.01]:
                    yield msprime.simulate(n, mutation_rate=mutrate,
                                           recombination_rate=recrate,
                                           length=200, random_seed=seed,
                                           model="dtwf")
                    seed += 1
                    population_configurations =[
                        msprime.PopulationConfiguration(
                        sample_size=n, initial_size=100),
                        msprime.PopulationConfiguration(
                        sample_size=n, initial_size=100)
                    ]
                    yield msprime.simulate(
                        population_configurations=population_configurations,
                        demographic_events=demographic_events,
                        recombination_rate=recrate,
                        mutation_rate=mutrate,
                        length=250, random_seed=seed,
                        model="dtwf")
                    seed += 1

    def get_slim_info(self, fname):
        # returns a dictionary whose keys are SLiM individual IDs, and whose values
        # are dictionaries with two entries:
        # - 'parents' is the SLiM IDs of the parents
        # - 'age' is a dictionary whose keys are tuples (SLiM generation, stage)
        #   and whose values are ages (keys not present are ones the indivdiual was
        #   not alive for)
        assert os.path.isfile(fname)
        out = {}
        with open(fname, 'r') as f:
            header = f.readline().split()
            assert header == ['generation', 'stage', 'individual', 'age', 'parent1', 'parent2']
            for line in f:
                gen, stage, ind, age, p1, p2 = line.split()
                gen = int(gen)
                ind = int(ind)
                age = int(age)
                parents = tuple([int(p) for p in (p1, p2) if p != "-1"])
                if ind not in out:
                    out[ind] = {
                            "parents" : parents,
                            "age" : {}
                            }
                else:
                    for p in parents:
                        assert p in out[ind]['parents']
                out[ind]['age'][(gen, stage)] = age
        return out

    def assertTablesEqual(self, t1, t2, label=''):
        # make it easy to see what's wrong
        if hasattr(t1, "metadata_schema"):
            if t1.metadata_schema != t2.metadata_schema:
                print(f"{label} :::::::::: t1 ::::::::::::")
                print(t1.metadata_schema)
                print(f"{label} :::::::::: t2 ::::::::::::")
                print(t2.metadata_schema)
            assert t1.metadata_schema == t2.metadata_schema
        if t1.num_rows != t2.num_rows:
            print(f"{label}: t1.num_rows {t1.num_rows} != {t2.num_rows} t2.num_rows")
        for k, (e1, e2) in enumerate(zip(t1, t2)):
            if e1 != e2:
                print(f"{label} :::::::::: t1 ({k}) ::::::::::::")
                print(e1)
                print(f"{label} :::::::::: t2 ({k}) ::::::::::::")
                print(e2)
            assert e1 == e2
        assert t1.num_rows == t2.num_rows
        assert t1 == t2

    def assertMetadataEqual(self, t1, t2):
        # check top-level metadata, first the parsed version:
        assert t1.metadata_schema == t2.metadata_schema
        assert t1.metadata == t2.metadata
        # and now check the underlying bytes
        # TODO: use the public interface if https://github.com/tskit-dev/tskit/issues/832 happens
        md1 = t1._ll_tables.metadata
        md2 = t2._ll_tables.metadata
        assert md1 == md2

    def verify_trees_equal(self, ts1, ts2):
        # check that trees are equal by checking MRCAs between randomly
        # chosen nodes with matching slim_ids
        random.seed(23)
        assert ts1.sequence_length == ts2.sequence_length
        if isinstance(ts1, tskit.TableCollection):
            ts1 = ts1.tree_sequence()
        if isinstance(ts2, tskit.TableCollection):
            ts2 = ts2.tree_sequence()
        map1 = {}
        for j, n in enumerate(ts1.nodes()):
            if n.metadata is not None:
                map1[n.metadata['slim_id']] = j
        map2 = {}
        for j, n in enumerate(ts2.nodes()):
            if n.metadata is not None:
                map2[n.metadata['slim_id']] = j
        assert set(map1.keys()) == set(map2.keys())
        sids = list(map1.keys())
        for sid in sids:
            n1 = ts1.node(map1[sid])
            n2 = ts2.node(map2[sid])
            assert n1.time == n2.time
            assert n1.metadata == n2.metadata
            i1 = ts1.individual(n1.individual)
            i2 = ts2.individual(n2.individual)
            assert i1.metadata == i2.metadata
        for _ in range(10):
            pos = random.uniform(0, ts1.sequence_length)
            t1 = ts1.at(pos)
            t2 = ts2.at(pos)
            for _ in range(10):
                a, b = random.choices(sids, k=2)
                assert t1.tmrca(map1[a], map1[b]) == t2.tmrca(map2[a], map2[b])

    def assertTableCollectionsEqual(self, t1, t2,
            skip_provenance=False, check_metadata_schema=True,
            reordered_individuals=False):
        if isinstance(t1, tskit.TreeSequence):
            t1 = t1.tables
        if isinstance(t2, tskit.TreeSequence):
            t2 = t2.tables
        t1_samples = [(n.metadata['slim_id'], j) for j, n in enumerate(t1.nodes) if (n.flags & tskit.NODE_IS_SAMPLE)]
        t1_samples.sort()
        t2_samples = [(n.metadata['slim_id'], j) for j, n in enumerate(t2.nodes) if (n.flags & tskit.NODE_IS_SAMPLE)]
        t2_samples.sort()
        t1.simplify([j for (_, j) in t1_samples], record_provenance=False)
        t2.simplify([j for (_, j) in t2_samples], record_provenance=False)
        if skip_provenance is True:
            t1.provenances.clear()
            t2.provenances.clear()
        if skip_provenance == -1:
            assert t1.provenances.num_rows + 1 == t2.provenances.num_rows
            t2.provenances.truncate(t1.provenances.num_rows)
            assert t1.provenances.num_rows == t2.provenances.num_rows
        if check_metadata_schema:
            # this is redundant now, but will help diagnose if things go wrong
            assert t1.metadata_schema.schema == t2.metadata_schema.schema
            assert t1.populations.metadata_schema.schema == t2.populations.metadata_schema.schema
            assert t1.individuals.metadata_schema.schema == t2.individuals.metadata_schema.schema
            assert t1.nodes.metadata_schema.schema == t2.nodes.metadata_schema.schema
            assert t1.edges.metadata_schema.schema == t2.edges.metadata_schema.schema
            assert t1.sites.metadata_schema.schema == t2.sites.metadata_schema.schema
            assert t1.mutations.metadata_schema.schema == t2.mutations.metadata_schema.schema
            assert t1.migrations.metadata_schema.schema == t2.migrations.metadata_schema.schema
        if not check_metadata_schema:
            # need to pull out metadata to compare as dicts before zeroing the schema
            m1 = t1.metadata
            m2 = t2.metadata
            ms = tskit.MetadataSchema(None)
            for t in (t1, t2):
                t.metadata_schema = ms
                t.populations.metadata_schema = ms
                t.individuals.metadata_schema = ms
                t.nodes.metadata_schema = ms
                t.edges.metadata_schema = ms
                t.sites.metadata_schema = ms
                t.mutations.metadata_schema = ms
                t.migrations.metadata_schema = ms
            t1.metadata = b''
            t2.metadata = b''
            assert m1 == m2
        if reordered_individuals:
            ind1 = {i.metadata['pedigree_id']: j for j, i in enumerate(t1.individuals)}
            ind2 = {i.metadata['pedigree_id']: j for j, i in enumerate(t2.individuals)}
            for pid in ind1:
                if not pid in ind2:
                    print("not in t2:", ind1[pid])
                assert pid in ind2
                if t1.individuals[ind1[pid]] != t2.individuals[ind2[pid]]:
                    print("t1:", t1.individuals[ind1[pid]])
                    print("t2:", t2.individuals[ind2[pid]])
                assert t1.individuals[ind1[pid]] == t2.individuals[ind2[pid]]
            for pid in ind2:
                if not pid in ind1:
                    print("not in t1:", ind2[pid])
                assert pid in ind1
            t1.individuals.clear()
            t2.individuals.clear()
        # go through one-by-one so we know which fails
        self.assertTablesEqual(t1.populations, t2.populations, "populations")
        self.assertTablesEqual(t1.individuals, t2.individuals, "individuals")
        self.assertTablesEqual(t1.nodes, t2.nodes, "nodes")
        self.assertTablesEqual(t1.edges, t2.edges, "edges")
        self.assertTablesEqual(t1.sites, t2.sites, "sites")
        self.assertTablesEqual(t1.mutations, t2.mutations, "mutations")
        self.assertTablesEqual(t1.migrations, t2.migrations, "migrations")
        self.assertTablesEqual(t1.provenances, t2.provenances, "provenances")
        self.assertMetadataEqual(t1, t2)
        assert t1.sequence_length == t2.sequence_length
        assert t1 == t2

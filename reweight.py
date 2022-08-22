#!/usr/bin/env python3

import hfst
from collections import defaultdict

MODES = ['lemma', 'lemmapos', 'tags']

def count(fname, mode):
    ret = defaultdict(lambda: 0)
    with open(fname) as fin:
        for line_ in fin:
            # TODO: escapes
            line = line_.strip().lstrip('^').rstrip('$')
            if not line:
                continue
            lus = line.split('+')
            if mode == 'lemma':
                for lu in lus:
                    ret[lu.split('<')[0]] += 1
            elif mode == 'lemmapos':
                for lu in lus:
                    ret[lu.split('>')[0]+'>'] += 1
            elif mode == 'tags':
                for lu in lus:
                    ret['<'+lu.split('<', 1)[1]] += 1
    return ret

def add_trans(fst, state, sym):
    nxt = fst.get_max_state() + 1
    fst.add_state(nxt)
    fst.add_transition(state, nxt, sym, sym)
    return nxt

def gen_single_fst(form, mode):
    fst = hfst.HfstBasicTransducer()
    cur = 0
    if mode in ['tags']:
        fst.add_state(1)
        cur = 1
        fst.add_transition(0, 1, hfst.EPSILON, hfst.EPSILON)
        fst.add_transition(1, 0, hfst.IDENTITY, hfst.IDENTITY)
    for sec in form.split('<'):
        if sec.endswith('>'):
            cur = add_trans(fst, cur, '<'+sec)
        else:
            for c in sec:
                cur = add_trans(fst, cur, c)
    if mode not in []:
        cur_was = cur
        cur = add_trans(fst, cur, hfst.EPSILON)
        fst.add_transition(cur, cur_was, hfst.IDENTITY, hfst.IDENTITY)
    fst.set_final_weight(cur, 1)
    return hfst.HfstTransducer(fst)

def gen_weighter(counts, mode):
    penalty = hfst.regex('?*')
    non_penalty = hfst.HfstTransducer()
    penalty_weight = max(counts.values()) + 1
    for form, count in counts.items():
        fst = gen_single_fst(form, mode)
        penalty.subtract(fst)
        fst.set_final_weights(penalty_weight-count)
        non_penalty.disjunct(fst)
    penalty.set_final_weights(penalty_weight)
    penalty.disjunct(non_penalty)
    return penalty

def weight(corpus, inname, outname, modes):
    fin = hfst.HfstInputStream(inname)
    trans = []
    while not fin.is_eof():
        trans.append(fin.read())
    fin.close()
    for m in modes:
        cts = count(corpus, m)
        pen = gen_weighter(cts, m)
        for t in trans:
            t.compose(pen)
    fout = hfst.HfstOutputStream(filename=outname)
    fout.write(trans)
    fout.close()

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser('reweight an analyzer based on a corpus')
    parser.add_argument('corpus')
    parser.add_argument('infile')
    parser.add_argument('outfile')
    parser.add_argument('-m', '--mode', action='append', choices=MODES)
    args = parser.parse_args()
    weight(args.corpus, args.infile, args.outfile, args.mode or [])

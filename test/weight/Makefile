all: weight-diff.tags.txt weight-diff.lemma.txt weight-diff.lemmapos.txt

weight-diff.%.txt: weight.%.hfst dix.hfst
	diff -U0 <(hfst-expand -w dix.hfst | sort) <(hfst-expand -w $< | sort) | dwdiff -u > $@ || exit 0

weight.%.hfst: corpus.txt dix.hfst
	../../reweight.py -m $* $^ $@

dix.hfst: dix.lexd
	lexd $< | hfst-txt2fst | hfst-invert > $@

SHELL=/bin/bash

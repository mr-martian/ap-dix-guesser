#!/usr/bin/env python3

import xml.etree.ElementTree as ET
import argparse
import re
from collections import defaultdict

parser = argparse.ArgumentParser('Make a guesser from a monodix')
parser.add_argument('src', action='store')
parser.add_argument('dest', action='store')
parser.add_argument('-r', '--regex', help='pattern for pardef name to match',
                    action='append')
args = parser.parse_args()

counts = defaultdict(lambda: 0)

def count_ents(sec, regs):
    global counts
    for ent in sec:
        last = ent[len(ent)-1]
        if last.tag != 'par': continue
        if any(r.match(last.attrib['n']) for r in regs):
            counts[last.attrib['n']] += 1

with open(args.src) as fin:
    tree = ET.parse(fin)
    regs = []
    for r in args.regex:
        regs.append(re.compile(r))
    if not regs:
        regs.append(re.compile('.*'))
    root = tree.getroot()
    for sec in root.findall('section'):
        count_ents(sec, regs)
        root.remove(sec)
    new_sec = ET.SubElement(root, 'section')
    for parname in sorted(counts.keys()):
        ent = ET.SubElement(new_sec, 'e')
        regex = ET.SubElement(ent, 're')
        regex.text = '[a-z]+' # TODO: language independence
        name = ET.SubElement(ent, 'p')
        l = ET.SubElement(name, 'l')
        r = ET.SubElement(name, 'r')
        r.text = '|' + parname.replace('/', '&') + '|'+str(counts[parname])+'|'
        par = ET.SubElement(ent, 'par')
        par.attrib['n'] = parname
        ent.tail = '\n'
    tree.write(args.dest, encoding='utf-8', xml_declaration=True)

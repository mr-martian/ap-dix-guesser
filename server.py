#!/usr/bin/env python3

from collections import defaultdict
from functools import partial
from http import HTTPStatus
import http.server
import json
import math
import os
import re
import shlex
import socketserver
from subprocess import Popen, PIPE
import sys
import threading
import time
import urllib.parse
import urllib.request
import shutil
import xml.etree.ElementTree
import zlib

class Analysis:
    def __init__(self, lemma, tags, paradigm=None, freq=0):
        self.lemma = lemma
        self.paradigm = paradigm
        self.freq = freq
        self.tags = tags
        self.guessed = bool(paradigm or freq)
    def from_stream(txt):
        par = None
        freq = 0
        if '|' in txt:
            ls = txt.split('|')
            par = ls[1].replace('&', '/')
            freq = int(ls[2])
            txt = ''.join([ls[0]] + ls[3:])
        # TODO: escaped < >
        txt = txt.replace('>', '')
        ls = txt.split('<')
        return Analysis(ls[0], ls[1:], par, freq)
    def to_json(self):
        return {
            'lemma': self.lemma,
            'paradigm': self.paradigm,
            'freq': self.freq,
            'tags': self.tags,
            'guessed': self.guessed,
        }

class LU:
    by_surface = {}
    by_lemma = defaultdict(list)
    def __init__(self, surface, analyses, sentence):
        self.surface = surface
        self.analyses = analyses
        self.sentences = [sentence]
        LU.by_surface[surface] = self
        for lm in set(a.lemma for a in analyses):
            LU.by_lemma[lm].append(self.surface)
    def add(surface, analyses, sentence):
        if surface in LU.by_surface:
            LU.by_surface[surface].sentences.append(sentence)
        else:
            LU(surface, analyses, sentence)
    def to_json(self):
        return {
            'surface': self.surface,
            'analyses': [a.to_json() for a in self.analyses],
            'sentences': self.sentences,
        }
    def all_guessed(self):
        return all(x.guessed for x in self.analyses)
    def top_surfs(count, guess_only):
        keys = [k for k,v in LU.by_surface.items()
                if not guess_only or v.all_guessed()]
        keys.sort()
        keys.sort(key=lambda k: len(LU.by_surface[k].sentences), reverse=True)
        return [LU.by_surface[k].to_json() for k in keys[:count]]
    def top_lemmas(count, guess_only):
        keys = [k for k,v in LU.by_lemma.items()
                if (not guess_only or
                    all(LU.by_surface[x].all_guessed() for x in v))]
        keys.sort() # alphabetize
        keys.sort(key=lambda k: len(LU.by_lemma[k]), reverse=True)
        return [[LU.by_surface[l].to_json() for l in LU.by_lemma[k]]
                for k in keys[:count]]

class StreamProcessor:
    blank_re = re.compile(r'^(\[([^\]\\]|\\.)\]|\\.|[^^])*')
    reading_re = re.compile(r'^([^/\\$]|\\.)+')
    def __init__(self, fst):
        self.fst = fst
        self.proc = None
        self.restart()
    def restart(self):
        self.proc = Popen(['lt-proc', '-z', self.fst],
                          stdin=PIPE, stdout=PIPE, stderr=PIPE)
    def esc(self, txt):
        ret = txt.replace('\\', '\\\\')
        for c in '^/$[]':
            ret = ret.replace(c, '\\'+c)
        return ret
    def process(self, sentence):
        # TODO: format handling?
        self.proc.stdin.write(self.esc(sentence).encode('utf-8'))
        self.proc.stdin.write(b'\0')
        self.proc.stdin.flush()
        chars = []
        while True:
            c = self.proc.stdout.read(1)
            if c == b'\0':
                break
            chars.append(c)
        self.tokenize(sentence, b''.join(chars).decode('utf-8'))
    def tokenize(self, sentence, output):
        while output:
            output = self.blank_re.sub('', output)
            if not output:
                break
            if output[0] != '^':
                # stream bad somehow, skip
                output = output[1:]
                continue
            output = output[1:]
            m = self.reading_re.match(output)
            if not m:
                # no surface form, skip
                continue
            surf = m.group(0)
            output = output[len(surf):]
            readings = []
            while output.startswith('/'):
                output = output[1:]
                m = self.reading_re.match(output)
                if not m:
                    continue
                rd = m.group(0)
                output = output[len(rd):]
                if rd.startswith('*'):
                    continue
                readings.append(Analysis.from_stream(rd))
            if output.startswith('$'):
                output = output[1:]
            if readings:
                LU.add(surf, readings, sentence)

def compress(s):
    step = 2 << 17
    producer = zlib.compressobj(level=9, wbits=15)
    idx = 0
    while idx < len(s):
        yield producer.compress(s[idx:idx+step])
        idx += step
    yield producer.flush()

THE_CALLBACK_LOCK = threading.Lock()

class CallbackRequestHandler(http.server.SimpleHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'

    def __init__(self, request, client_address, server, directory=None,
                 fst=None, guesser=None):
        self.fst = fst
        self.guesser = guesser
        super().__init__(request, client_address, server, directory=directory)

    def do_GET(self):
        parts = urllib.parse.urlsplit(self.path)
        if parts.path.strip('/') != 'callback':
            return super().do_GET()
        else:
            params = urllib.parse.parse_qs(parts.query)
            self.do_callback(params)

    def do_POST(self):
        ln = int(self.headers['Content-Length'])
        data = self.rfile.read(ln)
        self.do_callback(urllib.parse.parse_qs(data.decode('utf-8')))

    def send_json(self, status, blob):
        # based on https://github.com/PierreQuentel/httpcompressionserver/blob/master/httpcompressionserver.py (BSD license)
        self.send_response(status)
        self.send_header('Content-type', 'application/json')
        rstr = json.dumps(blob).encode('utf-8')
        self.send_header('Content-Encoding', 'deflate')
        if len(rstr) < (2 << 18):
            # don't bother chunking shorter messages
            dt = b''.join(compress(rstr))
            self.send_header('Content-Length', len(dt))
            self.end_headers()
            self.wfile.write(dt)
        else:
            self.send_header('Transfer-Encoding', 'chunked')
            self.end_headers()
            for data in compress(rstr):
                if data:
                    ln = hex(len(data))[2:].upper().encode('utf-8')
                    self.wfile.write(ln + b'\r\n' + data + b'\r\n')
            self.wfile.write(b'0\r\n\r\n')

    def do_callback(self, params):
        if 'a' not in params:
            resp = 'Parameter a must be passed!'
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-type", 'text/plain')
            self.send_header("Content-Length", len(resp))
            self.end_headers()
            self.wfile.write(resp.encode('utf-8'))
            return

        status = HTTPStatus.OK
        resp = {}
        shutdown = False
        action = params['a'][0]

        THE_CALLBACK_LOCK.acquire()

        if action == 'process':
            for l in params['t'][0].strip().splitlines():
                if not l.strip():
                    continue
                print(l)
                self.fst.process(l)
                self.guesser.process(l)
            resp['status'] = 'processed'
        elif action == 'list':
            count = int(params['c'][0])
            method = params['m'][0]
            guess_only = (params.get('g', ['no'])[0] == 'yes')
            if method == 'surf':
                resp['entries'] = LU.top_surfs(count, guess_only)
            elif method == 'lemma':
                resp['entries'] = LU.top_lemmas(count, guess_only)
            resp['method'] = method
        else:
            resp['error'] = 'unknown value for parameter a'

        self.send_json(status, resp)
        THE_CALLBACK_LOCK.release()
        if shutdown:
            if 'error' in resp:
                sys.exit(1)
            else:
                sys.exit(0)

class BigQueueServer(socketserver.ThreadingTCPServer):
    request_queue_size = 100

def start_server(port, fst, guesser):
    d = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'static/')
    f = StreamProcessor(fst)
    g = StreamProcessor(guesser)
    handle = partial(CallbackRequestHandler, directory=d, fst=f, guesser=g)
    print('Starting server')
    print('Open http://localhost:%d in your browser' % port)
    with BigQueueServer(('', port), handle) as httpd:
        try:
   	        httpd.serve_forever()
        except KeyboardInterrupt:
            print('')
            # the exception raised by sys.exit() gets caught by the
            # server, so we need to be a bit more drastic
            os._exit(0)

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser('TODO')
    parser.add_argument('-p', '--port', type=int, default=4000,
                        help='port to listen on')
    parser.add_argument('fst', action='store', help='standard dictionary')
    parser.add_argument('guesser', action='store',
                        help='generated guesser dictionary')
    args = parser.parse_args()
    start_server(args.port, args.fst, args.guesser)

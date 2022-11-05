#! /usr/bin/python3
import collections
import logging
import re
import subprocess
import sys
import time
import yaml


class Geometry(collections.namedtuple('Geometry', ('w', 'h'))):
    def __str__(self):
        return f"{self.w}x{self.h}"
Position = collections.namedtuple('Position', ('x', 'y'))
Display = collections.namedtuple('Display', ('geometry', 'position'))
Window = collections.namedtuple('Window', ('did', 'title', 'geometry'))

def get_geometry():
    # This returns the current geometry, and will center the laptop display under the other one (if any)
    #
    # Clearly, there are a few assumptions here:
    # - the laptop is situated under the other monitor
    # - there is at most a single monitor in addition to the laptop
    xrandr = subprocess.check_output(('xrandr', '--current'))
    displays = {}
    x, y = 0, 0
    primary = None
    for line in xrandr.decode(encoding='UTF-8').splitlines():
        m = re.match(r'^(?P<name>\S+) connected (?P<pri>primary )?'
                     r'(?:(?P<w>\d+)x(?P<h>\d+)\+(?P<x>\d+)\+(?P<y>\d+))',
                     line)
        if not m:
            continue
        if m.group('pri'):
            name = 'laptop'
            primary = m.group('name')
            x = int(m.group('x'))
            y = int(m.group('y'))
        else:
            name = 'monitor'
        displays[name] = Display(geometry=Geometry(w=int(m.group('w')), h=int(m.group('h'))),
                                 position=Position(x=int(m.group('x')), y=int(m.group('y'))))
    if len(displays) == 2:
        dx = (displays['monitor'].geometry.w - displays['laptop'].geometry.w) // 2
        dy = displays['monitor'].geometry.h
        if x != dx or y != dy:
            logging.info(f"centering primary display: {(x, y)} -> {(dx, dy)}")
            subprocess.call(('xrandr', '--output', primary, '--pos', f"{dx}x{dy}"),
                            stdout=sys.stdout, stderr=sys.stderr)
        return Geometry(w=displays['monitor'].geometry.w,
                        h=sum(map(lambda x: x.geometry.h, displays.values()))), displays
    else:
        # display position isn't updated right away somehow?
        name = list(displays.keys())[0]
        displays[name] = Display(geometry=displays[name].geometry,
                                 position=Position(x=0, y=0))
        return displays['laptop'].geometry, displays

def get_config(config_path):
    config = yaml.load(open(config_path, 'r'), Loader=yaml.SafeLoader)
    rules = config.get('rules', [])
    for i in range(len(rules)):
        rules[i]['title'] = re.compile(rules[i]['title'])
        if 'desktop' in rules[i]:
            rules[i]['desktop'] = str(rules[i]['desktop'])
        if 'geometry' in rules[i]:
            m = re.match('(?:(?P<w>\d+)x(?P<h>\d+))?(?:(?P<x>[+-]\d+)(?P<y>[+-]\d+))?',
                         rules[i]['geometry'])
            if not m:
                raise ValueError(f"invalid geometry: {rules[i]['geometry']}")
            rules[i]['geometry'] = Display(geometry=Geometry(w=m.group('w'), h=m.group('h')),
                                           position=Position(x=m.group('x'), y=m.group('y')))
    return config

def awmctrl(config_path, once):
    last = None
    config = None
    positions = {}
    while True:
        try:
            config = get_config(config_path)
        except FileNotFoundError:
            config = {}
        except Exception as e:
            if config is None:
                raise e
            logging.warning(f"invalid configuration: {e}")

        try:
            geometry, displays = get_geometry()
            if last != geometry and geometry in positions:
                move = True
            else:
                move = False
            if last != geometry:
                if last:
                    logging.info(f"new setup: {last} -> {geometry} {move=}")
                else:
                    logging.info(f"initial setup: {geometry}")
                logging.debug(f"displays: {displays}")

            new = {}
            wp = subprocess.check_output(('wmctrl', '-lG'))
            for window in wp.decode(encoding='UTF-8').splitlines():
                m = re.match(r'(?P<wid>0x[0-9a-f]+) +(?P<did>-?\d+) '
                             r'(?P<x>-?\d+)\s+(?P<y>-?\d+)\s+(?P<w>\d+)\s+(?P<h>\d+)\s+'
                             r'\S+\s+(?P<title>.+)', window)
                if m.group('did') == '-1': continue
                wgeometry = ','.join(('0', m.group('x'), m.group('y'), m.group('w'), m.group('h')))
                if move:
                    # move the windows back to where they were
                    if m.group('wid') in positions[geometry]:
                        window = positions[geometry][m.group('wid')]
                        if m.group('did') != window.did:
                            logging.debug(f"moving window '{m.group('title')}' to desktop {window.did}")
                            subprocess.call(('wmctrl', '-i', '-r', m.group('wid'), '-t', window.did),
                                            stdout=sys.stdout, stderr=sys.stderr)
                        if window.geometry != wgeometry:
                            logging.debug(f"moving window '{m.group('title')}' from {wgeometry} to {window.geometry}")
                            subprocess.call(('wmctrl', '-i', '-r', m.group('wid'), '-e', window.geometry),
                                            stdout=sys.stdout, stderr=sys.stderr)
                    else:
                        logging.info(f"not moving new window '{m.group('title')}'")
                else:
                    new[m.group('wid')] = Window(did=m.group('did'),
                                                 title=m.group('title'),
                                                 geometry=wgeometry)

            if geometry not in positions and config:
                logging.info('applying configured rules')
                rules = config.get('rules', [])
                for wid, window in new.items():
                    for rule in rules:
                        if rule.get('when', str(geometry)) != str(geometry):
                            continue
                        if not rule['title'].search(window.title):
                            continue
                        logging.debug(f"window '{window.title}' matches rule {rule}")
                        if window.did != rule.get('desktop', window.did):
                            logging.info(f"moving '{window.title}' to desktop {rule['desktop']}")
                            subprocess.call(('wmctrl', '-i', '-r', wid, '-t', rule['desktop']),
                                            stdout=sys.stdout, stderr=sys.stderr)
                        if (spec := rule.get('geometry')) \
                             and (display := displays.get(rule.get('display', 'laptop'))):
                            w, h = map(lambda x: int(x), window.geometry.split(',')[-2:])
                            if spec.geometry.w:
                                w, h = int(spec.geometry.w), int(spec.geometry.h)
                            if window.title.endswith('Google Chrome'):
                                w += 32
                                h += 32
                            if spec.position.x:
                                x = display.position.x + int(spec.position.x)
                                y = display.position.y + int(spec.position.y)
                                if spec.position.x[0] == '-':
                                    x += display.geometry.w - w
                                    if window.title.endswith('Google Chrome'):
                                        # Chrome window weirdness
                                        x += 32
                                elif window.title.endswith('Google Chrome'):
                                    # Chrome window weirdness
                                    x -= 16
                                if spec.position.y[0] == '-':
                                    y += display.geometry.h - h
                                    if window.title.endswith('Google Chrome'):
                                        # Chrome window weirdness
                                        y += 32
                            else:
                                x, y = map(lambda x: int(x), window.geometry.split(',')[1:3])
                            mvarg = ','.join(map(lambda x: str(x), ('0', x, y, w, h)))
                            if mvarg != window.geometry:
                                logging.info(f"moving '{window.title}' on {rule['display']} from {window.geometry[2:]} to {mvarg[2:]}")
                                subprocess.call(('wmctrl', '-i', '-r', wid, '-e', mvarg),
                                                stdout=sys.stdout, stderr=sys.stderr)
                        break

            now, _ = get_geometry()
            if now == geometry:
                last = geometry
                positions[last] = new
            else:
                logging.warning(f"geometry changed ({last} -> {now}) during {move=}, restarting update")
                continue
        except Exception as e:
            logging.error(f"error: {e}", exc_info=True)
        if once:
            return
        then = time.time()
        time.sleep(2)
        now = time.time()
        if now - then > 3:
            logging.info(f"took a {now - then:.0f} second nap")

def main():
    from optparse import OptionParser
    import os

    op = OptionParser(usage='%prog [ <options> ]')
    op.add_option('-1', dest='once', action='store_true', default=None,
                  help='Apply rules once and exit')
    op.add_option('-c', dest='config', action='store',
                  default=os.path.join(os.environ['HOME'], '.awmctrl'),
                  help='Configuration file')
    op.add_option('-C', dest='check', action='store_true', default=False,
                  help='Validate configuration and exit')
    op.add_option('-q', dest='quiet', action='store_true', default=False,
                  help='Less verbose logging')
    op.add_option('-v', dest='verbose', action='store_true', default=False,
                  help='More verbose logging')
    options, args = op.parse_args()
    if options.quiet and options.verbose:
        op.error('can be quiet or verbose, pick one!')
    if options.check and options.once:
        op.error('can validate config or run once, pick one!')

    logging.basicConfig(level=logging.DEBUG if options.verbose
                        else logging.ERROR if options.quiet else logging.INFO,
                        format='%(levelname).1s %(asctime).19s %(message)s')
    if options.check:
        get_config(options.config)
        sys.exit(0)

    awmctrl(options.config, options.once)
    sys.exit(0)


if __name__ == '__main__':
    main()

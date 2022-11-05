# awmctrl -- Automatically arrange windows based on desktop configuration

`awmctrl` is a simple wrapper around [`wmctrl(1)`](http://tripie.sweb.cz/utils/wmctrl/) and provides the following functionality:

* It can apply a set of pre-defined rules to position and resize windows based on their title
* It can keep track of where windows are, and reset their size and position when a second monitor is added or removed

## Dependencies

The following tools must be present on the system:

* `xrandr(1)`
* `wmctrl(1)`

## Limitations

`awmctrl` assumes a few things:

* there is either one or two monitors.
* when there are two monitors, the primary monitor is a laptop located below a single external monitor. (It will automatically be centered just below the monitor.)
* all (virtual) desktops have the same geometry

## Configuration file

The configuration file uses the YaML format.

```yaml
rules:
- title: Gmail
  when: 3840x2160
  desktop: 1
  geometry: 1600x1300-0+0
  display: laptop
```

Each rule supports the following options:

* `title`: a regular expression used to select the window
* `when`: the desktop geometry that this rule applies to. [OPTIONAL]
* `desktop`: the (virtual) desktop to move this window to. [OPTIONAL]
* `geometry`: the desired geometry for the window, using the `WIDTHxHEIGHT[+-]XPOS[+-]YPOS` format. `XPOS` and `YPOS` are relative to the display specified by `display`.
* `display`: this is either `laptop` (default) or `monitor`

## Usage

```
Usage: awmctrl [ <options> ]

Options:
  -h, --help  show this help message and exit
  -1          Apply rules once and exit
  -c CONFIG   Configuration file
  -C          Validate configuration and exit
  -q          Less verbose logging
  -v          More verbose logging
```

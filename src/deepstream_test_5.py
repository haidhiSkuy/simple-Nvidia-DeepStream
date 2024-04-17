import os
import sys

import gi
gi.require_version('Gst', '1.0')
from gi.repository import GLib, Gst

import pyds
from common.bus_call import bus_call
from common.is_aarch_64 import is_aarch64
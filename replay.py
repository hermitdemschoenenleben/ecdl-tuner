import json
import numpy as np
from utils import replay
from ben.plot import plt, set_font_scale, save_ma
from config import MODE_FREQUENCY_SPACING, TARGET_SLOPE

set_font_scale(2)

DATA_FOLDER = '../../data/frequency_control/rough_lock/'

st = 25
sc = 110.0
target_frequencies = [2e9, 4e9]

with open(DATA_FOLDER + 'data-%.2f-%.2f.json' % (st, sc), 'r') as f:
    data = json.load(f)

counter = [0]

curr, freq, curr_interval, slope, shift = (data['log'][4])
curr = np.array(curr) - curr[0]
freq = np.array(freq)

curr_interval = np.array(curr_interval)
shift -= (20*TARGET_SLOPE)

log = []

log.append((curr, freq, curr_interval+20, slope, shift))
shift -= MODE_FREQUENCY_SPACING
log.append((curr, freq, curr_interval-5, slope, shift))
shift += MODE_FREQUENCY_SPACING
log.append((curr, freq, curr_interval-5, slope, shift))


# = item

def fmt():
    plt.xlim((90, 140))
    plt.ylim((-4.5, 5))
    plt.xlabel(r'current in \SI{}{\milli\ampere}')
    plt.ylabel(r'offset frequency in \SI{}{\giga\hertz}')
    #plt.text(140, 2.5, "lock frequency", horizontalalignment='right')
    plt.tight_layout()
    save_ma('frequency_control/run/%d' % counter[0], pdf=True)
    counter[0] = counter[0] + 1

replay(target_frequencies, log, to_call=fmt)
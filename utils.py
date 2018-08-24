import numpy as np
from time import sleep, time
from scipy.optimize import curve_fit
from ben.devices import DLLException
from matplotlib import pyplot as plt
from config import CURRENT_LIMITS, DELTA_MODES, MODE_FREQUENCY_SPACING
import seaborn as sns

class TemperatureOutOfBounds(Exception):
    pass


class NoSlope(Exception):
    pass


class NotReachable(Exception):
    pass


def line(x, m, t):
    return (m * x) + t


def greater(x, y):
    return x if x > y else y


def smaller(x, y):
    return x if x < y else y


def in_range(value, range_):
    return value >= range_[0] and value <= range_[1]


def fit_line(curr, freq):
    [m, t], covariances = curve_fit(line, curr, freq)
    m_err, t_err = np.sqrt(np.diag(covariances))
    err = np.mean(np.abs([m_err / m, t_err / t]))

    if m > 0:
        # slope has wrong sign --> mirror it
        return True, -m, -t, err

    return False, m, t, err


def find_current_for_frequency(freq, m, t):
    return (freq - t) / m


def wait_for_stable_temperature(tec, tolerance=0.001):
    sleep(0.05)
    while True:
        try:
            while True:
                diff = np.abs(
                    (tec.get_temperature() - tec.get_target_temperature())
                )
                if diff < tolerance:
                    break

            break
        except DLLException:
            print('Exception')
            continue


def find_negative_ramp(ramp):
    new_slope = 0
    start_idx = None

    for idx, value in enumerate(ramp):
        if idx == 0:
            continue

        old_slope = new_slope
        new_slope = ramp[idx] - ramp[idx - 1]

        if start_idx is None and old_slope > 0 and new_slope <= 0:
            start_idx = idx

        if start_idx is not None and old_slope < 0 and new_slope >= 0:
            end_idx = idx
            break

    return slice(start_idx, end_idx)


def chunks(l, n):
    """Yield successive n-sized chunks from l."""
    for i in range(0, len(l), n):
        yield l[i:i + n]


def split_to_chunks(curr, freq):
    for split in range(1, 4):

        if split != 1:
            curr_intervals = chunks(curr, round(len(curr) / split))
            freq_intervals = chunks(freq, round(len(freq) / split))
        else:
            curr_intervals, freq_intervals = [curr], [freq]

        for curr_interval, freq_interval in zip(curr_intervals, freq_intervals):
            if len(curr_interval) < 5:
                continue

            yield curr_interval, freq_interval


def replay(target_frequencies, log, to_call=None):
    for item in log:
        if isinstance(item, tuple) or isinstance(item, list):
            if len(item) == 2:
                plt.plot(item[0], item[1])
                plt.show(block=True)
            else:
                curr, freq, curr_interval, slope, shift = item
                plot_ramp(
                    target_frequencies,
                    curr, freq, curr_interval, lambda x: line(x, slope, shift),
                    to_call=to_call
                )
                plt.show(block=True)
        else:
            print(item)


def plot_ramp(target_frequencies, curr, freq, curr_interval, fit, to_call=None):
    """
    Plot overview of current mode and extrapolated modes.
    """
    linewidth = 3
    palette = sns.color_palette()
    x = np.linspace(*CURRENT_LIMITS)
    plt.plot(x, [target_frequencies[0]/1e9] * len(x), color='black', linestyle='--', linewidth=linewidth)
    plt.plot(x, [target_frequencies[1]/1e9] * len(x), color='black', linestyle='--', linewidth=linewidth)

    for d in DELTA_MODES:
        if d == 0:
            color = palette[1]
        else:
            color = palette[0]
        plt.plot(x, (fit(x) + d * MODE_FREQUENCY_SPACING) / 1e9, linestyle='dotted', color=color, alpha=1, linewidth=linewidth)

    plt.plot(curr_interval, fit(np.array(curr_interval)) / 1e9, color=palette[1], linewidth=linewidth)

    #plt.plot(curr, freq, 'g')

    plt.ylim(
        smaller(min(freq) / 1e9, (target_frequencies[0]) / 1e9) - 0,
        greater(max(freq) / 1e9, (target_frequencies[1]) / 1e9) + 0,
    )

    plt.grid(True)

    if to_call is not None:
        to_call()

    plt.show()
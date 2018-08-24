import json
import numpy as np
from time import sleep
from matplotlib import pyplot as plt
from config import TARGET_SLOPE, CURRENT_LIMITS, MODE_FREQUENCY_SPACING, \
    DELTA_MODES, RAMP_AMPLITUDE, CURRENT_MOD_FACTOR, TARGET_CURRENTS, \
    MAX_TEMPERATURE, MIN_TEMPERATURE
from utils import split_to_chunks, fit_line, greater, smaller, in_range, \
    find_current_for_frequency, TemperatureOutOfBounds, NoSlope, NotReachable, \
    line

DATA_FOLDER = '../../data/frequency_control/rough_lock/'


class RoughLock:
    """
    This class actually performs the rough lock.
    """
    def __init__(self, frequency_control):
        self.fc = frequency_control
        self.vhbg_temperatures = []
        self.log_entries = []
        self.temperature_ramp_direction = False

    def start(self):
        target_frequency = np.mean(self.fc.target_frequencies)

        # record a current vs beat frequency diagram.
        # if no straight line is found that fulfils the criteria for
        # a laser mode, the current is wiggled up and down until a mode
        # is found.
        curr, freq, freq, curr_interval, freq_interval, slope, shift, \
            N_wiggles = self.search_laser_mode()

        if self.fc.debug:
            # save data for later analysis
            self.log((list(curr), list(freq), list(curr_interval), slope, shift))

        # pick a target mode and target current by extrapolating the
        # current mode and estimating which point could be reached
        delta_mode, target_current, temp_direction = \
            self.determine_target_mode(slope, shift)

        if delta_mode != 0:
            self.log(
                'ich will %d Moden %s' % (np.abs(delta_mode),
                'runter' if delta_mode > 0 else 'hoch')
            )

        N_temp_changes = 0
        error_counter = 0
        temp_ramp_started = False
        temperature_ramp_did_turn = False

        # this loop runs until rough lock is complete or has failed
        while True:
            if self.fc.debug:
                # for debugging
                #self.vhbg_temperatures.append(self.fc.electronics.get_vhbg_temperature())
                #self.log('%.2fdeg' % self.vhbg_temperatures[-1])
                pass

            # tune the current to a value that is far away and return again
            # by chosing the right current limit, we try to force a mode hop
            # to the mode we want to reach
            self.fc.laser_current = CURRENT_LIMITS[
                1 if temp_direction < 0 else 0
            ]
            sleep(.3)
            self.fc.laser_current = target_current
            sleep(.7)

            # record a current vs beat frequency diagram once again
            curr, freq = self.fc.electronics.measure_frequencies(
                self.fc.laser_current
            )
            # already prepare the ramp measurement of the next iteration
            # this was added for a special combination of lab devices which
            # require some time to prepare a ramp measurement
            # --> this is not strictly necessary, but improves performance
            self.fc.electronics.prepare_ramp_measurement()

            # analyse the recorded data and try to find a slope corresponding
            # to a laser mode
            data = self.find_slope(curr, freq)

            if data is None:
                if self.fc.debug:
                    self.log((list(curr), list(freq)))

                # no slope found... this may happen if our beat note is close
                # to 0 or too high for the counter
                # --> start a temperature ramp (if it wasn't started before)
                if not temp_ramp_started:
                    self.ramp_temperature(temp_direction)
                    temp_ramp_started = True

                error_counter += 1
                self.log('no laser mode found #%d' % error_counter)

                if temperature_ramp_did_turn:
                    if error_counter == 25:
                        #  it's hopeless. We just don't find the laser mode again
                        raise TemperatureOutOfBounds()
                elif error_counter == 7:
                    # we waited some time while ramping the VHBG temperature in
                    # one direction but did not find a laser mode. Let's try to
                    # go in the other direction.
                    temp_direction *= -1
                    self.ramp_temperature(temp_direction)
                    temperature_ramp_did_turn = True
                    error_counter = 0
                    self.log('searching for a laser mode in the other vhbg direction')

                continue

            # if we are here, a laser mode was found!
            error_counter = 0
            temperature_ramp_did_turn = False

            # unpack the data describing the current mode
            freq, curr_interval, freq_interval, slope, shift = data
            current_mode = lambda x: line(x, slope, shift)

            if self.fc.debug:
                # save data for later analysis
                self.log((list(curr), list(freq), list(curr_interval), slope, shift))

            # the data we recorded contains a laser mode, but may also contain
            # some noisy data
            # --> this is a hypothetic ideal mode
            extrapolated = current_mode(curr)
            freq_range = (min(extrapolated), max(extrapolated))
            mean_freq = np.mean(freq_range)
            center_frequency = current_mode(self.fc.laser_current)

            # check whether both desired frequencies are within the current mode
            if in_range(self.fc.target_frequencies[0], freq_range) and \
                    in_range(self.fc.target_frequencies[1], freq_range):
                # Yes! We're done!
                self.ramp_temperature(False)
                return N_temp_changes, N_wiggles

            very_far_away = np.abs(center_frequency - target_frequency) > \
                0.8 * MODE_FREQUENCY_SPACING

            if very_far_away:
                # we are too far from our target frequency in order to reach it
                # without a mode hop. Start a VHBG temperature ramp in the right
                # direction in order to move mode boundaries in our favor
                if not temp_ramp_started:
                    self.ramp_temperature(temp_direction)
                    temp_ramp_started = True
                else:
                    if (mean_freq > 0 and temp_direction < 0) or \
                       (mean_freq < 0 and temp_direction > 0):
                        # apparently we are tuning the temperature in the wrong
                        # direction
                        self.log('change temperature direction')
                        temp_direction *= -1
                        self.ramp_temperature(temp_direction)
            else:
                # we are not very far away from our target frequency,
                # it may be reached by setting the MO current.
                # Try it out!
                self.ramp_temperature(False)
                target_current = find_current_for_frequency(
                    target_frequency, slope, shift
                )

    def cleanup(self):
        """
        Save log file for later debugging.
        """
        sc = self.fc.start_current
        st = self.fc.start_temperature
        f = open(DATA_FOLDER + 'data-%.2f-%.2f.json' % (st, sc), 'w')
        json.dump({
            'start_current': sc,
            'start_temperature': st,
            'vhbg_temperatures': self.vhbg_temperatures,
            'log': self.log_entries
        }, f)
        f.close()

    def log(self, item):
        if isinstance(item, str):
            print(item)
        self.log_entries.append(item)

    def is_good_slope(self, m):
        """
        Check whether the slope of a fitted lined roughly corresponds
        to the slope of a laser mode.
        """
        diff = np.abs((TARGET_SLOPE - m) / TARGET_SLOPE)
        return diff < 0.2

    def wiggle_current(self, start_current):
        """
        Returns an iterator over currents lower and higher than the given one.
        """
        yield start_current

        for i in range(1, 10):
            high = start_current + (i * 3)
            low = start_current - (i * 3)
            if high + (RAMP_AMPLITUDE * CURRENT_MOD_FACTOR) < CURRENT_LIMITS[1]:
                yield high
            if low - (RAMP_AMPLITUDE * CURRENT_MOD_FACTOR) > CURRENT_LIMITS[0]:
                yield low

    def find_slope(self, curr, freq):
        """
        Splits data into segments and checks for each segment whether a
        line with the right slope for a laser mode is visible.
        """
        chunks = split_to_chunks(curr, freq)
        for i, [curr_interval, freq_interval] in enumerate(chunks):
            mirror, slope, shift, err = fit_line(curr_interval, freq_interval)
            current_mode = lambda x: line(x, slope, shift)

            print(slope)

            if self.is_good_slope(slope) and err < 1e-2:
                if mirror:
                    freq_interval = -1 * np.array(freq_interval)
                    freq = -1 * np.array(freq)

                return freq, curr_interval, freq_interval, slope, shift

    def search_laser_mode(self):
        """
        Checks whether we see a laser mode. If no, wiggles the current
        up and down until we find a good slope.
        """
        currents = self.wiggle_current(self.fc.start_current)

        for N_wiggles, current in enumerate(currents):
            if N_wiggles != 0:
                self.fc.laser_current = current
                sleep(0.5)

            curr, freq = self.fc.electronics.measure_frequencies(
                self.fc.laser_current
            )

            self.fc.electronics.prepare_ramp_measurement()

            data = self.find_slope(curr, freq)

            if data is not None:
                break

            self.log('no slope found')
            self.log((list(curr), list(freq)))
        else:
            raise NoSlope()

        # we found a laser mode!
        freq, curr_interval, freq_interval, slope, shift = data

        return curr, freq, freq, curr_interval, freq_interval, slope, shift, \
            N_wiggles

    def determine_target_mode(self, slope, shift):
        """
        Extrapolates the current mode and estimates which mode could be suitable
        for reaching both desired frequencies.
        """
        # iterate over possible modes, starting with the current one
        # (delta=0) first
        for delta_mode in DELTA_MODES:
            # find the offset of the mode
            mode_shift = shift - (delta_mode * MODE_FREQUENCY_SPACING)

            # extrapolate the mode in question and check which currents would
            # be needed to reach the desired frequencies
            target_currents = [
                find_current_for_frequency(f, slope, mode_shift)
                for f in self.fc.target_frequencies
            ]
            # are these currents allowed?
            currents_valid = [
                in_range(c, TARGET_CURRENTS) for c in target_currents
            ]

            if currents_valid[0] and currents_valid[1]:
                # the currents are allowed, we now have a new target mode
                self.log(
                    'target currents are %.2f and %.2f' % \
                    tuple(sorted(target_currents))
                )

                target_current = np.mean(target_currents)

                if delta_mode == 0:
                    # we want to stay in the current mode
                    # ramp the vhbg temperature in a direction that shifts
                    # the mode in the right direction
                    temp_ramp_direction = 1 \
                        if target_current - self.fc.start_current > 0 \
                        else -1
                else:
                    # we want to go to a different mode
                    # ramp the vhbg temperature in a direction that will
                    # eventually allow us to reach it
                    temp_ramp_direction = 1 if delta_mode > 0 else -1

                return delta_mode, target_current, temp_ramp_direction
        else:
            raise NotReachable()

    def ramp_temperature(self, temp_direction):
        """
        Start a vhbg temperature ramp.
        """
        self.log('ramp temperature, direction %d' % temp_direction)

        if not temp_direction:
            if self.temperature_ramp_direction:
                temp_correction  = -.5 * self.temperature_ramp_direction

                self.log('correct %.2f' % temp_correction)

                self.fc.vhbg_target_temperature = \
                    self.fc.electronics.get_vhbg_temperature() + temp_correction
        else:
            sign = temp_direction
            self.fc.vhbg_target_temperature = \
                MAX_TEMPERATURE if sign > 0 else MIN_TEMPERATURE

        self.temperature_ramp_direction = temp_direction

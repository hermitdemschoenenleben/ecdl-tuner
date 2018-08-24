class Lock:
    def __init__(self, redpitaya):
        self.redpitaya = redpitaya
        self.pid = self.redpitaya.pid

    def start(self):
        self.pid.integrator_reset([False, False, False, False])
        self.pid.set_setpoint(0, 4000)

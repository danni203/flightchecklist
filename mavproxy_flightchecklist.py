#!/usr/bin/env python
'''
Interactive Pre-Flight Checklist Module for MAVProxy
'''

from MAVProxy.modules.lib import mp_module
import math
import time
import socket

class ChecklistModule(mp_module.MPModule):
    def __init__(self, mpstate):
        super(ChecklistModule, self).__init__(mpstate, "checklist", "Step-by-step pre-flight checklist")
        
        self.MYPORT = 5601
        self.RXIP = "localhost" # Change to "192.168.1.113" if on a separate GCS machine
        self.s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        
        self.add_command('check', self.cmd_check, "Run pre-flight checklist", ['start', 'ok', 'dash', 'engine', 'radio', 'status', 'abort'])
        
        self.current_step = -1
        
        # Split Engine and Radio into two distinct tasks
        self.task_list = [
            {"name": "Physical Checks", "done": False},
            {"name": "Telemetry Validation", "done": False},
            {"name": "Attitude Sensors (Accel/Mag)", "done": False},
            {"name": "Airspeed Calibration", "done": False},
            {"name": "Flight Controls & Surfaces", "done": False},
            {"name": "Engine & Powertrain", "done": False},
            {"name": "Radio & Communications", "done": False},
            {"name": "Final Commit", "done": False}
        ]
        
        # Standard Telemetry Store
        self.live_data = {
            'voltage': 0.0, 'battery_pct': 0, 'fix_type': 0, 'sats': 0,
            'pitch': 0.0, 'roll': 0.0, 'yaw': 0.0, 'airspeed': 0.0, 'heading': 0, 'mode': 'UNKNOWN'
        }
        
        # JetCat Turbine Store
        self.jetcat_data = {
            'state': "OFF", 'rpm': 0, 'rpm_set': 0, 'throttle': 0, 'throttle_set': 0,
            'egt': 0.0, 'pump_v': 0.0, 'thrust': 0.0, 'fuel_flow': 0.0, 'fuel_cons': 0.0, 'fuel_pct': 0
        }
        
        # Radio & Comms Store
        self.radio_data = {
            'rssi': 0, 'remrssi': 0, 'txbuf': 0, 
            'rc_active': False, 'ch1': 0, 'ch2': 0, 'ch3': 0, 'ch4': 0, 
            'gcs_last_seen': 0.0 
        }
        
        # Added both new step functions to the sequence
        self.steps = [
            self.step_physical, self.step_telemetry, self.step_attitude,        
            self.step_airspeed, self.step_flight_surfaces, 
            self.step_engine, self.step_radio, self.step_final
        ]

    def broadcast_step_state(self, step_num, state_val):
        '''
        Broadcasts the checklist state over UDP XML strings.
        step_num: 1-8
        state_val: 0 (Pending), 1 (Active), 2 (Done)
        '''
        target_id = f"CHECKLIST.step{step_num}"
        
        # Build the exact XML string your layout engine parses
        send_string = f'<set id="{target_id}" value="{state_val}"/>\n'
        
        try:
            # Send the UDP packet
            self.s.sendto(send_string.encode('utf-8'), (self.RXIP, self.MYPORT))
        except Exception as e:
            # Silently catch network errors so it doesn't crash MAVProxy
            pass
    def mavlink_packet(self, m):
        '''Silently intercepts messages to feed the Dashboards'''
        mtype = m.get_type()
        
        if mtype == 'SYS_STATUS':
            self.live_data['voltage'] = m.voltage_battery / 1000.0
            self.live_data['battery_pct'] = m.battery_remaining
        elif mtype == 'GPS_RAW_INT':
            self.live_data['fix_type'] = m.fix_type
            self.live_data['sats'] = m.satellites_visible
        elif mtype == 'ATTITUDE':
            self.live_data['pitch'] = math.degrees(m.pitch)
            self.live_data['roll'] = math.degrees(m.roll)
            self.live_data['yaw'] = math.degrees(m.yaw)
        elif mtype == 'VFR_HUD':
            self.live_data['airspeed'] = m.airspeed
            self.live_data['heading'] = m.heading
            
        elif mtype == 'HEARTBEAT':
            sysid = m.get_srcSystem()
            if sysid == 1: 
                self.live_data['mode'] = self.mpstate.status.flightmode
            elif sysid == 255: 
                self.radio_data['gcs_last_seen'] = time.time()
                
        elif mtype == 'JETCAT_FULL_DATA':
            state_map = {0: "OFF", 1: "STANDBY", 2: "IGNITE", 3: "ACCELERATE", 4: "STABILIZE", 11: "RUNNING", 7: "COOLING"}
            self.jetcat_data['state'] = state_map.get(m.turbine_state, f"STATE_{m.turbine_state}")
            self.jetcat_data['rpm'] = m.rpm_actual
            self.jetcat_data['rpm_set'] = m.rpm_setpoint
            self.jetcat_data['throttle'] = m.throttle_pct
            self.jetcat_data['throttle_set'] = m.throttle_setpoint_pct
            self.jetcat_data['egt'] = m.egt_celsius
            self.jetcat_data['pump_v'] = m.pump_voltage_actual
            self.jetcat_data['thrust'] = m.thrust_newtons
            self.jetcat_data['fuel_flow'] = m.fuel_flow
            self.jetcat_data['fuel_cons'] = m.fuel_consumed
            self.jetcat_data['fuel_pct'] = m.fuel_pct

        elif mtype == 'RADIO_STATUS':
            self.radio_data['rssi'] = m.rssi
            self.radio_data['remrssi'] = m.remrssi
            self.radio_data['txbuf'] = m.txbuf
            
        elif mtype == 'RC_CHANNELS':
            self.radio_data['rc_active'] = True if m.chan3_raw > 800 else False
            self.radio_data['ch1'] = m.chan1_raw
            self.radio_data['ch2'] = m.chan2_raw
            self.radio_data['ch3'] = m.chan3_raw
            self.radio_data['ch4'] = m.chan4_raw

    def cmd_check(self, args):
        if len(args) == 0:
            return self.print_usage()
        cmd = args[0].lower()

        if cmd == 'start':
            # 1. Reset all tasks internally AND broadcast PENDING (0) to the UI
            for i, task in enumerate(self.task_list): 
                task["done"] = False
                self.broadcast_step_state(i + 1, 0)
                
            self.current_step = 0
            self.print_overall_status()
            
            # 2. Broadcast Step 1 as ACTIVE (1) to the UI
            self.broadcast_step_state(self.current_step + 1, 1)
            self.run_current_step()
            
        elif cmd == 'ok':
            if self.current_step == -1: 
                return print("Checklist not started. Type 'check start'")
                
            if self.current_step < len(self.task_list): 
                self.task_list[self.current_step]["done"] = True
                # 3. Broadcast the completed step as DONE (2) to the UI
                self.broadcast_step_state(self.current_step + 1, 2)
                
            self.current_step += 1
            self.print_overall_status()
            
            if self.current_step < len(self.steps): 
                # 4. Broadcast the NEW current step as ACTIVE (1) to the UI
                self.broadcast_step_state(self.current_step + 1, 1)
                self.run_current_step()
            else:
                print("\n>>> FLIGHT CLEARANCE GRANTED. YOU ARE READY TO ARM. <<<\n")
                self.current_step = -1
                
        elif cmd == 'dash': self.print_dashboard()
        elif cmd == 'engine': self.print_engine_dash()
        elif cmd == 'radio': self.print_radio_dash()
        elif cmd == 'status': self.print_overall_status()
        elif cmd == 'abort':
            print("\n[!] CHECKLIST ABORTED [!]\n")
            # 5. Broadcast PENDING (0) to wipe the UI clean on abort
            for i in range(len(self.task_list)):
                self.broadcast_step_state(i + 1, 0)
            self.current_step = -1
        else: self.print_usage()

    def print_usage(self): 
        print("Usage: check <start | ok | dash | engine | radio | status | abort>")

    def print_overall_status(self):
        print("\n" + "="*50)
        print("            MASTER CHECKLIST PROGRESS            ")
        print("="*50)
        for i, task in enumerate(self.task_list):
            mark = "[ OK ]" if task["done"] else "[    ]"
            pointer = "->" if i == self.current_step else "  "
            print(f" {pointer} {mark} Step {i+1}: {task['name']}")
        print("="*50 + "\n")

    def print_dashboard(self):
        print("\n" + "-"*45)
        print("          FLIGHT STATUS DASHBOARD          ")
        print("-"*45)
        print(f" MODE:     {self.live_data['mode']}")
        print(f" POWER:    {self.live_data['voltage']:.2f}v  |  {self.live_data['battery_pct']}% Remaining")
        print(f" GPS:      Fix: {self.live_data['fix_type']}   |  Sats: {self.live_data['sats']}")
        print(" . . . . . . . . . . . . . . . . . . . . . . ")
        print(f" ACCEL:    Pitch: {self.live_data['pitch']:>5.1f}° | Roll: {self.live_data['roll']:>5.1f}°")
        print(f" MAG:      Heading: {self.live_data['heading']:>3}°")
        print(f" AIRSPEED: {self.live_data['airspeed']:.2f} m/s")
        print("-"*45 + "\n")

    def print_engine_dash(self):
        print("\n" + "="*50)
        print("              JETCAT TURBINE STATUS              ")
        print("="*50)
        print(f" STATE:      [{self.jetcat_data['state']}]")
        print(f" RPM:        {self.jetcat_data['rpm']}  (Target: {self.jetcat_data['rpm_set']})")
        print(f" THROTTLE:   {self.jetcat_data['throttle']}%  (Target: {self.jetcat_data['throttle_set']}%)")
        print(f" EGT:        {self.jetcat_data['egt']:.1f} °C")
        print("-" * 50)
        print(f" PUMP VOLTS: {self.jetcat_data['pump_v']:.2f} v")
        print(f" THRUST:     {self.jetcat_data['thrust']:.1f} N")
        print("-" * 50)
        print(f" FUEL FLOW:  {self.jetcat_data['fuel_flow']:.1f} ml/min")
        print(f" FUEL REM:   {self.jetcat_data['fuel_pct']}%  ({self.jetcat_data['fuel_cons']:.0f} ml consumed)")
        print("="*50 + "\n")

    def print_radio_dash(self):
        gcs_alive = (time.time() - self.radio_data['gcs_last_seen']) < 5.0
        gcs_status = "[ CONNECTED ]" if gcs_alive else "[ DISCONNECTED ]"
        rc_status = "[ ACTIVE ]" if self.radio_data['rc_active'] else "[ NO RC DETECTED ]"
        
        print("\n" + "="*50)
        print("               COMMUNICATIONS LINK               ")
        print("="*50)
        print(" 1. GCS MACHINE (Heartbeat 255):")
        print(f"    Status:      {gcs_status}")
        print("-" * 50)
        print(" 2. HERELINK CONTROLLER (RC Input):")
        print(f"    Status:      {rc_status}")
        print(f"    Sticks PWM:  R:{self.radio_data['ch1']}  P:{self.radio_data['ch2']}  T:{self.radio_data['ch3']}  Y:{self.radio_data['ch4']}")
        print("-" * 50)
        print(" 3. COMDAM TELEMETRY (Radio Status):")
        print(f"    Local RSSI:  {self.radio_data['rssi']} / 255")
        print(f"    Remote RSSI: {self.radio_data['remrssi']} / 255")
        print(f"    Tx Buffer:   {self.radio_data['txbuf']}%")
        print("="*50 + "\n")

    def run_current_step(self):
        print("*"*55)
        self.steps[self.current_step]()
        if self.current_step < len(self.steps):
            print("-" * 55)
            print(">>> Commands: 'check dash', 'check engine', 'check radio'")
            print(">>> Type 'check ok' to MARK AS DONE and proceed.")
            print("*"*55 + "\n")

    # --- STEP DEFINITIONS ---
    def step_physical(self):
        print(f"STEP 1: {self.task_list[0]['name']}")
        print("[ ] Perform Weight & Balance")
        print("[ ] Connect tether to launcher")

    def step_telemetry(self):
        print(f"STEP 2: {self.task_list[1]['name']}")
        print("[ ] ACTION: Type 'check dash' to verify GPS has 3D Fix")
        print("[ ] ACTION: Type 'check dash' to verify Battery Voltage is nominal")

    def step_attitude(self):
        print(f"STEP 3: {self.task_list[2]['name']}")
        print("[ ] ACTION: Pitch UP. Type 'check dash' to verify ACCEL Pitch is positive.")
        print("[ ] ACTION: Roll RIGHT WING DOWN. Type 'check dash' to verify ACCEL Roll.")
        print("[ ] ACTION: Rotate NORTH. Type 'check dash' to verify MAG Heading.")

    def step_airspeed(self):
        print(f"STEP 4: {self.task_list[3]['name']}")
        print("Zeroing airspeed sensor...")
        self.mpstate.functions.process_stdin("calpress")
        time.sleep(1) 
        print("[ ] Airspeed zeroed. Blow into pitot tube and type 'check dash'.")

    def step_flight_surfaces(self):
        print(f"STEP 5: {self.task_list[4]['name']}")
        #self.mpstate.functions.process_stdin("mode FBWA")
        print("[ ] ACTION: Tilt AV. Check control surface reactions (FBWA).")
        print("[ ] ACTION: Switch to MANUAL mode on radio. Check surface trims.")

    # --- THE SPLIT STEPS ---
    def step_engine(self):
        print(f"STEP 6: {self.task_list[5]['name']}")
        print("[ ] ACTION: Clear Prop/Jet Area.")
        print("[ ] ACTION: Type 'check engine' to monitor Turbine ECU data.")

    def step_radio(self):
        print(f"STEP 7: {self.task_list[6]['name']}")
        print("[ ] ACTION: Type 'check radio' to verify COMDAM, Herelink, and GCS links.")

    def step_final(self):
        print(f"STEP 8: {self.task_list[7]['name']}")
        print("[ ] Launcher video stream active")
        print("[ ] Aircraft video stream active")

def init(mpstate): return ChecklistModule(mpstate)

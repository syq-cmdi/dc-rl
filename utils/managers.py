import os
import numpy as np
import pandas as pd
import psychrolib as psy

file_path = os.path.abspath(__file__)
PATH = os.path.split(os.path.dirname(file_path))[0]

# Set the unit system for psychrolib
psy.SetUnitSystem(psy.SI)

class CoherentNoise:
    """Class to add coherent noise to the data.

        Args:
            base (List[float]): Base data
            weight (float): Weight of the noise to be added
            desired_std_dev (float, optional): Desired standard deviation. Defaults to 0.1.
            scale (int, optional): Scale. Defaults to 1.
    """
    def __init__(self, base, weight, desired_std_dev=0.1, scale=1):
        """Initialize CoherentNoise class

        Args:
            base (List[float]): Base data
            weight (float): Weight of the noise to be added
            desired_std_dev (float, optional): Desired standard deviation. Defaults to 0.1.
            scale (int, optional): Scale. Defaults to 1.
        """
        self.base = base
        self.weight = weight
        self.desired_std_dev = desired_std_dev
        self.scale = scale

    def generate(self, n_steps):
        """
        Generate coherent noise 

        Args:
            n_steps (int): Length of the data to generate.

        Returns:
            numpy.ndarray: Array of generated coherent noise.
        """
        steps = np.random.normal(loc=0, scale=self.scale, size=n_steps)
        random_walk = np.cumsum(self.weight * steps)
        normalized_noise = (random_walk / np.std(random_walk)) * self.desired_std_dev
        return self.base + normalized_noise


# Function to normalize a value v given a minimum and a maximum
def normalize(v, min_v, max_v):
    """Function to normalize values

    Args:
        v (float): Value to be normalized
        min_v (float): Lower limit
        max_v (float): Upper limit

    Returns:
        float: Normalized value
    """
    return (v - min_v)/(max_v - min_v)

# Function to generate cosine and sine values for a given hour and day
def sc_obs(current_hour, current_day):
    """Generate sine and cosine of the hour and day

    Args:
        current_hour (int): Current hour of the day
        current_day (int): Current day of the year

    Returns:
        List[float]: Sine and cosine of the hour and day
    """
    # Normalize and round the current hour and day
    two_pi = np.pi * 2

    norm_hour = round(current_hour/24, 3) * two_pi
    norm_day = round((current_day)/365, 3) * two_pi
    
    # Calculate cosine and sine values for the current hour and day
    cos_hour = np.cos(norm_hour)*0.5 + 0.5
    sin_hour = np.sin(norm_hour)*0.5 + 0.5
    cos_day = np.cos(norm_day)*0.5 + 0.5
    sin_day = np.sin(norm_day)*0.5 + 0.5
    
    return [cos_hour, sin_hour, cos_day, sin_day]


class Time_Manager():
    """Class to manage the time dimenssion over an episode

        Args:
            init_day (int, optional): Day to start from. Defaults to 0.
            days_per_episode (int, optional): Number of days that an episode would last. Defaults to 30.
            timezone_shift (int, optional): Shift for the timezone. Defaults to 0.
    """
    def __init__(self, init_day=0, days_per_episode=30, timezone_shift=0):
        """Initialize the Time_Manager class.

        Args:
            init_day (int, optional): Day to start from. Defaults to 0.
            days_per_episode (int, optional): Number of days that an episode would last. Defaults to 30.
            timezone_shift (int, optional): Shift for the timezone. Defaults to 0.
        """
        self.init_day = init_day
        self.timestep_per_hour = 4
        self.days_per_episode = days_per_episode
        self.timezone_shift = timezone_shift
        
        # Calculate the total timesteps for the episode based on init_day
        self.simulated_total_timesteps = (self.days_per_episode * 24 * self.timestep_per_hour)
        self.current_timestep = 0

    def reset(self, init_day=None, init_hour=None):
        """Reset the time manager to a specific initial day and hour."""
        self.day = init_day if init_day is not None else self.init_day
        self.hour = init_hour if init_hour is not None else self.timezone_shift

        # Recalculate the current timestep based on day/hour
        self.current_timestep = int(self.day * 24 * self.timestep_per_hour + self.hour * self.timestep_per_hour)
        self.total_timesteps = self.current_timestep + self.simulated_total_timesteps
        return sc_obs(self.hour, self.day)

        
    def step(self):
        """Step function for the time maneger

        Returns:
            List[float]: Current hour and day in sine and cosine form.
            bool: Signal if the episode has reach the end.
        """
        self.current_timestep += 1
        self.hour += 1 / self.timestep_per_hour
        if self.hour >= 24:
            self.hour = 0
            self.day += 1
        return self.day, self.hour, sc_obs(self.hour, self.day), self.isterminal()
    
    def isterminal(self):
        """Function to identify terminal state

        Returns:
            bool: Signals if a state is terminal or not
        """
        return self.current_timestep >= self.total_timesteps



# Class to manage CPU workload data
class Workload_Manager():
    def __init__(self, workload_filename='', init_day=0, future_steps=4, weight=0.005, desired_std_dev=0.01, timezone_shift=0, debug=False):
        """Manager of the DC workload.

        Args:
            workload_filename (str, optional): Filename of the CPU data. Defaults to ''. Should be a .csv file containing the CPU hourly normalized workload data between 0 and 1. Should contain 'cpu_load' column.
            init_day (int, optional): Initial day of the episode. Defaults to 0.
            future_steps (int, optional): Number of steps of the workload forecast. Defaults to 4.
            weight (float, optional): Weight value for coherent noise. Defaults to 0.01.
            desired_std_dev (float, optional): Desired standard deviation for coherent noise. Defaults to 0.025.
            timezone_shift (int, optional): Shift for the timezone. Defaults to 0.
        """
        
        # Load CPU data from a CSV file
        # One year data=24*365=8760
        if workload_filename == '':
            cpu_data_list = pd.read_csv(PATH+'/data/Workload/Alibaba_CPU_Data_Hourly_1.csv')['cpu_load'].values[:8760]
        else:
            cpu_data_list = pd.read_csv(PATH+f'/data/Workload/{workload_filename}')['cpu_load'].values[:8760]

        assert len(cpu_data_list) == 8760, "The number of data points in the workload data is not one year data=24*365=8760."

        cpu_data_list = cpu_data_list.astype(float)
        self.time_step = 0
        self.future_steps = future_steps
        self.timestep_per_hour = 4
        self.time_steps_day = self.timestep_per_hour*24
        self.init_day = init_day
        self.timezone_shift = timezone_shift

        # Interpolate the CPU data to increase the number of data points
        x = range(0, len(cpu_data_list))
        xcpu_new = np.linspace(0, len(cpu_data_list), len(cpu_data_list)*self.timestep_per_hour)  
        self.cpu_smooth = np.interp(xcpu_new, x, cpu_data_list)
        
        # Shift the data to match the timezone shift
        self.cpu_smooth =  np.roll(self.cpu_smooth, -1*self.timezone_shift*self.timestep_per_hour)
        
        # Save a copy of the original data
        self.original_data = self.cpu_smooth.copy()
                
        # Initialize CoherentNoise process
        self.coherent_noise = CoherentNoise(base=0, weight=weight, desired_std_dev=desired_std_dev)
        
        # Debug mode
        self.debug = debug

    def smooth_workload(self, window_size=3):
        """Apply moving average to smooth out workload changes.

        Args:
            window_size (int): The size of the moving window. Defaults to 3.

        Returns:
            np.array: Smoothed workload data.
        """
        return np.convolve(self.cpu_smooth, np.ones(window_size) / window_size, mode='same')


    # Function to return all workload data
    def get_total_wkl(self):
        """Get current workload

        Returns:
            List[float]: CPU data
        """
        return np.array(self.cpu_smooth[self.time_step:])

    def scale_array(self, arr):
        """
        Scales the input array so that approximately 90% of its values
        fall within the range of 0.2 to 0.8, based on the 5th and 95th percentiles.
        
        Parameters:
        arr (np.array): The input numpy array to be scaled.
        
        Returns:
        np.array: The scaled numpy array.
        """
        
        # Calculate the 5th and 95th percentiles of the array
        p5 = np.percentile(arr, 5)
        p95 = np.percentile(arr, 95)
        
        # Scale the array based on the percentiles, without clipping
        # This ensures values outside the 5th to 95th percentile range naturally
        # fall outside the 0.2 to 0.8 range.
        scaled_arr = 0.2 + ((arr - p5) * (0.8 - 0.2) / (p95 - p5))
        
        # Clip values to be within 0 to 1
        scaled_arr = np.clip(scaled_arr, 0, 1)
        
        return scaled_arr

    # Function to reset the time step and return the workload at the first time step
    def reset(self, init_day=None, init_hour=None):
        """Reset Workload_Manager to a specific initial day and hour.

        Args:
            init_day (int, optional): Day to start from. If None, defaults to the initial day set during initialization.
            init_hour (int, optional): Hour to start from. If None, defaults to 0.

        Returns:
            float: CPU workload at current time step.
        """
        self.time_step = (init_day if init_day is not None else self.init_day) * self.time_steps_day + (init_hour if init_hour is not None else 0) * self.timestep_per_hour
        self.init_time_step = self.time_step
        
        baseline = np.random.random()*0.5 - 0.25
        
        # if not self.debug:
        # Add noise to the workload data using the CoherentNoise 
        cpu_data = self.original_data# * np.random.uniform(0.95, 1.05, len(self.original_data))
        # print(f'Check the original cpu data: {self.original_data} and the coherent noise: {self.coherent_noise.generate(len(cpu_data))}')
        cpu_smooth = cpu_data# * 0.7 + self.coherent_noise.generate(len(cpu_data)) * 0.3 + baseline
        
        self.cpu_smooth = self.scale_array(cpu_smooth)
        
        # Apply smoothing method
        self.cpu_smooth = self.smooth_workload(window_size=16)
        
        # num_roll_weeks = np.random.randint(0, 52) # Random roll the workload because is independed on the month, so I am rolling across weeks (52 weeks in a year)
        # self.cpu_smooth =  np.roll(self.cpu_smooth, num_roll_weeks*self.timestep_per_hour*24*7)
        
        # else:
            # Fixed utilization for debugging using 60% of the CPU
            # self.cpu_smooth = np.ones_like(self.cpu_smooth) * 0.6

        self._current_workload = self.cpu_smooth[self.time_step]
        self._next_workload = self.cpu_smooth[self.time_step + 1]
        return self._current_workload
        
    # Function to advance the time step and return the workload at the new time step
    def step(self):
        """Step function for the Workload_Manager

        Returns:
            float: CPU workload at current time step
            float: Amount of daily flexible workload
        """
        self.time_step += 1
        
        # If it tries to read further, restart from the inital day
        if self.time_step >= len(self.cpu_smooth):
            self.time_step = self.init_time_step
        
        self._current_workload = self.cpu_smooth[self.time_step]
        self._next_workload = self.cpu_smooth[self.time_step + 1]
        
        # assert self.time_step < len(self.cpu_smooth), f'Episode length: {self.time_step} is longer than the provide cpu_smooth: {len(self.cpu_smooth)}'
        return self._current_workload  # to avoid logical error
    
    def get_current_workload(self):
        return self._current_workload

    def get_next_workload(self):
        return self._next_workload
    
    def set_current_workload(self, workload):         
        self.cpu_smooth[self.time_step] = workload
        
    def get_n_next_workloads(self, n):
        return self.cpu_smooth[self.time_step+1:self.time_step+1+n]


# Class to manage carbon intensity data
class CI_Manager():
    """Manager of the carbon intensity data.

    Args:
        filename (str, optional): Filename of the carbon intensity data. Defaults to ''.
        location (str, optional): Location identifier. Defaults to 'NYIS'.
        init_day (int, optional): Initial day of the episode. Defaults to 0.
        future_steps (int, optional): Number of steps of the CI forecast. Defaults to 4.
        weight (float, optional): Weight value for coherent noise. Defaults to 0.1.
        desired_std_dev (float, optional): Desired standard deviation for coherent noise. Defaults to 5.
        timezone_shift (int, optional): Shift for the timezone. Defaults to 0.
    """
    def __init__(self, filename='', location='NYIS', init_day=0, future_steps=4, weight=0.1, desired_std_dev=5, timezone_shift=0, debug=False):
        """Initialize the CI_Manager class.

        Args:
            filename (str, optional): Filename of the carbon intensity data. Defaults to ''.
            location (str, optional): Location identifier. Defaults to 'NYIS'.
            init_day (int, optional): Initial day of the episode. Defaults to 0.
            future_steps (int, optional): Number of steps of the CI forecast. Defaults to 4.
            weight (float, optional): Weight value for coherent noise. Defaults to 0.1.
            desired_std_dev (float, optional): Desired standard deviation for coherent noise. Defaults to 5.
            timezone_shift (int, optional): Shift for the timezone. Defaults to 0.
        """
        # Load carbon intensity data from a CSV file
        # One year data=24*365=8760
        if not location == '':
            carbon_data_list = pd.read_csv(PATH+f"/data/CarbonIntensity/{location}_NG_&_avgCI.csv")['avg_CI'].values[:8760]
        else:
            carbon_data_list = pd.read_csv(PATH+f"/data/CarbonIntensity/{filename}")['avg_CI'].values[:8760]

        assert len(carbon_data_list) == 8760, "The number of data points in the carbon intensity data is not one year data=24*365=8760."
        self.debug = debug
        carbon_data_list = carbon_data_list.astype(float)
        self.init_day = init_day
        self.timezone_shift = timezone_shift

        self.timestep_per_hour = 4
        self.time_steps_day = self.timestep_per_hour*24
        
        # Handle nan values just in case. Replace with average value
        if np.isnan(carbon_data_list).any():
            avg_value = np.nanmean(carbon_data_list)
            carbon_data_list = np.nan_to_num(carbon_data_list, nan=avg_value)
        
        # If self.debug is True, replace the carbon intensity data with a sine wave for testing of 24 timesteps of period but with the same length of the carbon intensity data
        # if self.debug:
            # Create a sine wave with 24 timesteps of period (one day cycle) and the same length as carbon_data_list
            # t = np.arange(len(carbon_data_list)*4)  # Create an array of timesteps equal to the length of the carbon data
            # carbon_data_list = np.sin(2 * np.pi * t / self.time_steps_day) * 0.5 + 0.5  # Create sine wave with period of 24 timesteps (one day)
    
            
        x = range(0, len(carbon_data_list))
        xcarbon_new = np.linspace(0, len(carbon_data_list), len(carbon_data_list)*self.timestep_per_hour)
        
        # Interpolate the carbon data to increase the number of data points
        self.carbon_smooth = np.interp(xcarbon_new, x, carbon_data_list)
        
        # Shift the data to match the timezone shift
        self.carbon_smooth =  np.roll(self.carbon_smooth, -1*self.timezone_shift*self.timestep_per_hour)

        # Save a copy of the original data
        self.original_data = self.carbon_smooth.copy()
        
        self.time_step = 0

        # Initialize CoherentNoise process
        self.coherent_noise = CoherentNoise(base=0, weight=weight, desired_std_dev=desired_std_dev)
        
        self.future_steps = future_steps
        
        
        

    # Function to return all carbon intensity data
    def get_total_ci(self):
        """Function to obtain the total carbon intensity

        Returns:
            List[float]: Total carbon intesity
        """
        return self.carbon_smooth[self.time_step:]

    def reset(self, init_day=None, init_hour=None):
        """Reset CI_Manager to a specific initial day and hour.

        Args:
            init_day (int, optional): Day to start from. If None, defaults to the initial day set during initialization.
            init_hour (int, optional): Hour to start from. If None, defaults to 0.

        Returns:
            float: Carbon intensity at current time step.
            float: Normalized carbon intensity at current time step and its forecast.
        """
        self.time_step = (init_day if init_day is not None else self.init_day) * self.time_steps_day + (init_hour if init_hour is not None else 0) * self.timestep_per_hour

        # Add noise to the carbon data using the CoherentNoise
        self.carbon_smooth = self.original_data# + self.coherent_noise.generate(len(self.original_data))
        
        self.carbon_smooth = np.clip(self.carbon_smooth, 0, None)
        
        # num_roll_days = np.random.randint(0, 14) # Random roll the workload some days. I can roll the carbon intensity up to 14 days.
        # self.carbon_smooth =  np.roll(self.carbon_smooth, num_roll_days*self.timestep_per_hour*24)

        # if self.debug:
            # Expand the range of the carbon intensity data x10
            # self.carbon_smooth = (self.carbon_smooth - min(self.carbon_smooth)*0.3) * 10
        self.min_ci = min(self.carbon_smooth)
        self.max_ci = max(self.carbon_smooth)
        # self.norm_carbon = normalize(self.carbon_smooth, self.min_ci, self.max_ci)
        # self.norm_carbon = (self.carbon_smooth - np.mean(self.carbon_smooth)) / np.std(self.carbon_smooth)
        
        # Normalize the carbon intensity data using the next 30 days of data
        # mean_30_days = np.mean(self.carbon_smooth[self.time_step:30*self.time_steps_day + self.time_step])
        # std_30_days = np.std(self.carbon_smooth[self.time_step:30*self.time_steps_day + self.time_step])
        # self.norm_carbon = (self.carbon_smooth - mean_30_days) / std_30_days
        # Scale the carbon intensity data using the min max calues of the next 30 days
        max_30_days = np.max(self.carbon_smooth[self.time_step:30*self.time_steps_day + self.time_step])
        min_30_days = np.min(self.carbon_smooth[self.time_step:30*self.time_steps_day + self.time_step])
        self.norm_carbon = (self.carbon_smooth - min_30_days) / (max_30_days - min_30_days)
        # self.norm_carbon = (np.clip(self.norm_carbon, -1, 1) + 1) * 0.5
        # if self.debug:
            # self.norm_carbon = self.carbon_smooth
        
        self._current_carbon_smooth = self.carbon_smooth[self.time_step]
        self._next_carbon_smooth = self.carbon_smooth[self.time_step + 1]
        
        self._current_norm_carbon = self.norm_carbon[self.time_step]
        self._next_norm_carbon = self.norm_carbon[self.time_step + 1]
        self._forecast_norm_carbon = self.norm_carbon[(self.time_step+1):(self.time_step+1)+self.future_steps]

        return self._current_norm_carbon, self._forecast_norm_carbon, self._current_carbon_smooth
    
    # Function to advance the time step and return the carbon intensity at the new time step
    def step(self):
        """Step CI_Manager

        Returns:
            float: Carbon intensity at current time step
            float: Normalized carbon intensity at current time step and it's forecast
        """
        self.time_step +=1
        
        # If it tries to read further, restart from the initial index
        if self.time_step >= len(self.carbon_smooth):
            self.time_step = self.init_day*self.time_steps_day
            
        # Renormalize every 24 hours (self.time_steps_day)
        # if self.time_step % self.time_steps_day == 0:
        #     self.renormalize_current_day()

        self._current_carbon_smooth = self.carbon_smooth[self.time_step]
        self._current_norm_carbon = self.norm_carbon[self.time_step]
        self._next_norm_carbon = self.norm_carbon[self.time_step + 1]
        self._forecast_norm_carbon = self.norm_carbon[(self.time_step+1):(self.time_step+1)+self.future_steps]

        return self._current_norm_carbon, self._forecast_norm_carbon, self._current_carbon_smooth
    
    def get_current_ci(self):
        return self._current_norm_carbon
    
    def get_forecast_ci(self):
        return self._forecast_norm_carbon
    
    def get_n_past_ci(self, n):
        return self.norm_carbon[self.time_step-n:self.time_step]

# Class to manage weather data
# Where to obtain other weather files:
# https://climate.onebuilding.org/
class Weather_Manager():
    """Manager of the weather data.
       Where to obtain other weather files:
       https://climate.onebuilding.org/

    Args:
        filename (str, optional): Filename of the weather data. Defaults to ''.
        location (str, optional): Location identifier. Defaults to 'NY'.
        init_day (int, optional): Initial day of the year. Defaults to 0.
        weight (float, optional): Weight value for coherent noise. Defaults to 0.02.
        desired_std_dev (float, optional): Desired standard deviation for coherent noise. Defaults to 0.75.
        temp_column (int, optional): Column that contains the temperature data. Defaults to 6.
        rh_column (int, optional): Column that contains the relative humidity data. Defaults to 8.
        pres_column (int, optional): Column that contains the pressure data. Defaults to 9.
        timezone_shift (int, optional): Shift for the timezone. Defaults to 0.
    """
    def __init__(self, filename='', location='NY', init_day=0, weight=0.02, desired_std_dev=0.75, temp_column=6, rh_column=8, pres_column=9, timezone_shift=0, debug=False):
        """Initialize the Weather_Manager class.

        Args:
            filename (str, optional): Filename of the weather data. Defaults to ''.
            location (str, optional): Location identifier. Defaults to 'NY'.
            init_day (int, optional): Initial day of the year. Defaults to 0.
            weight (float, optional): Weight value for coherent noise. Defaults to 0.02.
            desired_std_dev (float, optional): Desired standard deviation for coherent noise. Defaults to 0.75.
            temp_column (int, optional): Column that contains the temperature data. Defaults to 6.
            rh_column (int, optional): Column that contains the relative humidity data. Defaults to 8.
            pres_column (int, optional): Column that contains the pressure data. Defaults to 9.
            timezone_shift (int, optional): Shift for the timezone. Defaults to 0.
        """
        # Load weather data from a CSV file

        if not location == '':
            weather_data = pd.read_csv(PATH+f'/data/Weather/{location}', skiprows=8, header=None).values
        else:
            weather_data = pd.read_csv(PATH+f'/data/Weather/{filename}', skiprows=8, header=None).values
        
        # The weather data has a granularity of 1 hour, so we need to interpolate it to have a granularity of 15 minutes
        temperature_data = weather_data[:,temp_column].astype(float)
        relative_humidity_data = weather_data[:,rh_column].astype(float)  # Added for relative humidity
        pressure_data = weather_data[:,pres_column].astype(float)  # Added for atmospheric pressure
                
        self.wet_bulb_data = [psy.GetTWetBulbFromRelHum(t, rh / 100, p) for t, rh, p in zip(temperature_data, relative_humidity_data, pressure_data)]

        # Normalize wet bulb temperature data
        self.min_wb_temp = 0
        self.max_wb_temp = 45

        self.init_day = init_day
        # One year data=24*365=8760
        x = range(0, len(temperature_data))
        self.timestep_per_hour = 4

        xtemperature_new = np.linspace(0, len(temperature_data), len(temperature_data)*self.timestep_per_hour )
        
        self.min_temp = 0
        self.max_temp = 45
        
        # Interpolate the data to increase the number of data points
        self.wet_bulb_data = np.interp(xtemperature_new, x, self.wet_bulb_data)
        self.norm_wet_bulb_data = normalize(self.wet_bulb_data, self.min_wb_temp, self.max_wb_temp)

        self.temperature_data = np.interp(xtemperature_new, x, temperature_data)
        self.norm_temp_data = normalize(self.temperature_data, self.min_temp, self.max_temp)

        self.time_step = 0
        self.timezone_shift = timezone_shift
        
        # Shift the data to match the timezone shift
        self.temperature_data =  np.roll(self.temperature_data, -1*self.timezone_shift*self.timestep_per_hour)
        self.wet_bulb_data =  np.roll(self.wet_bulb_data, -1*self.timezone_shift*self.timestep_per_hour)

        # Save a copy of the original data
        self.original_temp_data = self.temperature_data.copy()
        self.original_wb_data = self.wet_bulb_data.copy()

        # Initialize CoherentNoise process
        self.coherent_noise = CoherentNoise(base=0, weight=weight, desired_std_dev=desired_std_dev)
                
        self.time_steps_day = self.timestep_per_hour*24
        
        self.debug = debug

    # Function to return all weather data
    def get_total_weather(self):
        """Obtain the weather data in a List form

        Returns:
            List[form]: Total temperature data
        """
        return self.temperature_data[self.time_step:]

    # Function to reset the time step and return the weather at the first time step
    def reset(self, init_day=None, init_hour=None):
        """Reset Weather_Manager to a specific initial day and hour.

        Args:
            init_day (int, optional): Day to start from. If None, defaults to the initial day set during initialization.
            init_hour (int, optional): Hour to start from. If None, defaults to 0.

        Returns:
            tuple: Temperature at current step, normalized temperature at current step, wet bulb temperature at current step, normalized wet bulb temperature at current step.
        """

        self.time_step = (init_day if init_day is not None else self.init_day) * self.time_steps_day + (init_hour if init_hour is not None else 0) * self.timestep_per_hour
        
        if not self.debug:
            # Add noise to the temperature data using the CoherentNoise
            coh_noise = self.coherent_noise.generate(len(self.original_temp_data))
            # print(f'TODO: check the generated coherent noise: {coh_noise[:3]} and the original temperature data: {self.original_temp_data[:3]} and the wet bulb data: {self.original_wb_data[:3]}' )
            self.temperature_data = self.original_temp_data + coh_noise
            self.wet_bulb_data = self.original_wb_data + coh_noise
            
            num_roll_days = np.random.randint(0, 14) # Random roll the temperature some days.
            self.temperature_data =  np.roll(self.temperature_data, num_roll_days*self.timestep_per_hour*24)
            self.wet_bulb_data =  np.roll(self.wet_bulb_data, num_roll_days*self.timestep_per_hour*24)

            self.temperature_data = np.clip(self.temperature_data, self.min_temp, self.max_temp)
            max_30_days = np.max(self.temperature_data[self.time_step:30*self.time_steps_day + self.time_step])
            min_30_days = np.min(self.temperature_data[self.time_step:30*self.time_steps_day + self.time_step])
            self.norm_temp_data = (self.temperature_data - min_30_days) / (max_30_days - min_30_days)
            
            self.wet_bulb_data = np.clip(self.wet_bulb_data, self.min_wb_temp, self.max_wb_temp)
            max_30_days = np.max(self.wet_bulb_data[self.time_step:30*self.time_steps_day + self.time_step])
            min_30_days = np.min(self.wet_bulb_data[self.time_step:30*self.time_steps_day + self.time_step])
            self.norm_wet_bulb_data = (self.wet_bulb_data - min_30_days) / (max_30_days - min_30_days)
            
        else:
            # Use a fixed temperature for debugging and wet bulb temperature
            self.temperature_data = np.ones_like(self.temperature_data) * 30
            self.norm_temp_data = np.ones_like(self.norm_temp_data) * 0.5
            self.wet_bulb_data = np.ones_like(self.wet_bulb_data) * 25
            
        self._current_temp = self.temperature_data[self.time_step]
        self._next_temp = self.temperature_data[self.time_step + 1]
        self._current_norm_temp = self.norm_temp_data[self.time_step]
        self._next_norm_temp = self.norm_temp_data[self.time_step + 1]
        self._current_wet_bulb = self.wet_bulb_data[self.time_step]
        self._current_norm_wet_bulb = self.norm_wet_bulb_data[self.time_step]
        
        return self._current_temp, self._current_norm_temp, self._current_wet_bulb, self._current_norm_wet_bulb

    
    
    # Function to advance the time step and return the weather at the new time step
    def step(self):
        """Step on the Weather_Manager

        Returns:
            float: Temperature a current step
            float: Normalized temperature a current step
        """
                
        self.time_step += 1
        
        # If it tries to read further, restart from the initial index
        if self.time_step >= len(self.temperature_data):
            self.time_step = self.init_day*self.time_steps_day
            
        self._current_temp = self.temperature_data[self.time_step]
        self._next_temp = self.temperature_data[self.time_step + 1]
        self._current_norm_temp = self.norm_temp_data[self.time_step]
        self._next_norm_temp = self.norm_temp_data[self.time_step + 1]
        self._current_wet_bulb = self.wet_bulb_data[self.time_step]
        self._current_norm_wet_bulb = self.norm_wet_bulb_data[self.time_step]
            
        return self._current_temp, self._current_norm_temp, self._current_wet_bulb, self._current_norm_wet_bulb
    
    def get_current_temperature(self):
        return self._current_norm_temp
    
    def get_next_temperature(self):
        return self._next_norm_temp
    
    def get_n_next_temperature(self, n):
        return self.norm_temp_data[self.time_step+1:self.time_step+1+n]
    
    def get_current_wet_bulb(self):
        return self._current_wet_bulb
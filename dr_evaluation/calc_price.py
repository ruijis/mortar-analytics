from electricitycostcalculator.cost_calculator.cost_calculator import CostCalculator
from electricitycostcalculator.openei_tariff.openei_tariff_analyzer import *
from electricitycostcalculator.cost_calculator.tariff_structure import *
from .get_greenbutton_id import *
import datetime as dtime
import numpy as np
import pandas as pd
import math
import os

calculator = CostCalculator()
PROJECT_ROOT = os.path.abspath(os.path.dirname(__file__))+'/'

def eval_nan(x):
    if (not type(x) == str) and math.isnan(x):
        return None
    return x

def calc_price(power_vector, site, start_datetime, end_datetime):
    tarrifs = pd.read_csv(os.path.join(PROJECT_ROOT, 'tariffs.csv'), index_col='meter_id')
    meter_id = get_greenbutton_id(site)
    tariff = tarrifs.loc[meter_id]
    tariff = dict(tariff)
    tariff['distrib_level_of_interest'] = eval_nan(tariff['distrib_level_of_interest'])
    tariff['option_exclusion'] = eval_nan(tariff['option_exclusion'])
    tariff['option_mandatory'] = eval_nan(tariff['option_mandatory'])
    total_price = calc_total_price(power_vector, tariff, start_datetime, end_datetime)
    return total_price

def calc_total_price(power_vector, tariff_options, start_datetime, end_datetime, interval='15min'):
    '''
    returns the total energy cost of power consumption over the given window
    the granularity is determined from the length of the vector and the time window
    TODO: Demand charges

    power_vector: a pandas series of power consumption (kW) over the given window
    tariff_options: a dictionary of the form {
        utility_id: '14328',
        sector: 'Commercial',
        tariff_rate_of_interest: 'A-1 Small General Service', 
        distrib_level_of_interest=None, #TODO: Figure out what this is
        phasewing='Single',
        tou=True
    }
    start_datetime: the datetime object representing the start time (starts )
    end_datetime: the datetime object representing the start time
    '''
    time_delta = end_datetime - start_datetime
    interval_15_min = (3600*24*time_delta.days + time_delta.seconds)/(60*15)
    if len(power_vector) == interval_15_min or interval == '15min':
        energy_vector = power_15min_to_hourly_energy(power_vector)
        energy_vector.index = pd.date_range(start=start_datetime, end=end_datetime, freq='1h')
    else:
        energy_vector = power_vector
    energy_vector = energy_vector / 1000
    if pd.isna(tariff_options['phasewing']):
        tariff_options['phasewing'] = 'Single'
    tariff = OpenEI_tariff(tariff_options['utility_id'],
                  tariff_options['sector'],
                  tariff_options['tariff_rate_of_interest'], 
                  tariff_options['distrib_level_of_interest'],
                  tariff_options['phasewing'],
                  tariff_options['tou'],
                  option_exclusion=tariff_options['option_exclusion'],
                  option_mandatory=tariff_options['option_mandatory'])
    tariff.read_from_json()
    tariff_struct_from_openei_data(tariff, calculator, pdp_event_filenames='PDP_events.json')
    pd_prices, map_prices = calculator.get_electricity_price(timestep=TariffElemPeriod.HOURLY,
                                                        range_date=(start_datetime.replace(tzinfo=pytz.timezone('US/Pacific')),
                                                                    end_datetime.replace(tzinfo=pytz.timezone('US/Pacific'))))
    pd_prices = pd_prices.fillna(0)
    energyPrices = pd_prices.customer_energy_charge.values + pd_prices.pdp_non_event_energy_credit.values + pd_prices.pdp_event_energy_charge.values
    demandPrices = pd_prices.customer_demand_charge_season.values + pd_prices.pdp_non_event_demand_credit.values + pd_prices.customer_demand_charge_tou.values
    return energyPrices @ energy_vector

def power_15min_to_hourly_energy(power_vector):
    energy_kwh = np.array(power_vector / 4.0) #TODO: Array or time-index series?
    result = pd.Series(np.sum(energy_kwh.reshape(-1, 4), axis=1))
    return result
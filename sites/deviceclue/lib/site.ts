export const site = {
  name: 'DeviceClue',
  url: 'https://deviceclue.site',
  description: 'Understand the signal. Find the next step. Clear, source-led answers about appliance settings, equipment symbols, and everyday faults.',
};
export const categories = [
  { id: 'ovens', name: 'Ovens & cookers', short: 'Ovens', description: 'Clock settings and cooking symbols', icon: 'oven' },
  { id: 'cooling', name: 'Cooling & ice', short: 'Cooling', description: 'Fridge dials and ice machine alarms', icon: 'snowflake' },
  { id: 'home-systems', name: 'Home systems', short: 'Home systems', description: 'Thermostats and garage door openers', icon: 'home' },
  { id: 'batteries', name: 'Batteries & charging', short: 'Batteries', description: 'Charger messages and battery condition', icon: 'battery' },
  { id: 'small-engines', name: 'Small engines', short: 'Small engines', description: 'Choke controls and starting symbols', icon: 'engine' },
  { id: 'dishwashers', name: 'Dishwashers', short: 'Dishwashers', description: 'Drainage, fault codes and programme symbols', icon: 'dishwasher' },
] as const;

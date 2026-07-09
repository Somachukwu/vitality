export const mockVitals = {
  timestamp: new Date().toISOString(),
  heartRate: 74, spo2: 97.5, temperature: 36.8, humidity: 62, weight: 72.4, steps: 8240,
};

export function mockVitalsHistory(days = 7) {
  const out = [];
  const now = Date.now();
  for (let i = days * 24; i >= 0; i--) {
    const t = now - i * 3600 * 1000;
    out.push({
      timestamp: new Date(t).toISOString(),
      heartRate: 70 + Math.round(Math.sin(i / 6) * 8 + Math.random() * 6),
      spo2: 96 + Math.random() * 2,
      temperature: 36.5 + Math.random() * 0.7,
      weight: 72 + Math.sin(i / 40) * 0.6,
    });
  }
  return out;
}

export const mockMeals = [
  {
    id: 'meal_1',
    timestamp: new Date(Date.now() - 3 * 3600 * 1000).toISOString(),
    imageUrl: 'https://images.unsplash.com/photo-1604908176997-125f25cc6f3d?w=300&q=70',
    detectedFoods: [
      { name: 'Jollof Rice', portionSize: '1 cup', calories: 340, carbs: 65, protein: 8, fat: 6 },
      { name: 'Grilled Chicken', portionSize: '150g', calories: 210, carbs: 0, protein: 36, fat: 7 },
      { name: 'Fried Plantain', portionSize: '4 slices', calories: 180, carbs: 28, protein: 1, fat: 7 },
    ],
    totalCalories: 730,
  },
  {
    id: 'meal_2',
    timestamp: new Date(Date.now() - 8 * 3600 * 1000).toISOString(),
    imageUrl: 'https://images.unsplash.com/photo-1565299624946-b28f40a0ae38?w=300&q=70',
    detectedFoods: [
      { name: 'Akara', portionSize: '3 pieces', calories: 220, carbs: 18, protein: 9, fat: 12 },
      { name: 'Pap (Ogi)', portionSize: '1 bowl', calories: 150, carbs: 32, protein: 3, fat: 1 },
    ],
    totalCalories: 370,
  },
];

export const mockRecommendations = [
  {
    id: 'rec_1', timestamp: new Date(Date.now() - 30 * 60 * 1000).toISOString(),
    type: 'nutrition',
    message: "You've reached 8,200 steps and are 340 calories under your daily goal. A light protein-rich snack like moi moi or boiled eggs before 8PM would round out your day nicely.",
    triggerData: 'Triggered by: step count + remaining calorie budget',
    severity: 'info',
  },
  {
    id: 'rec_2', timestamp: new Date(Date.now() - 5 * 3600 * 1000).toISOString(),
    type: 'health_alert',
    message: 'Your SpO₂ briefly dipped to 93% around noon. Try a few minutes of deep breathing and stay well-hydrated this afternoon.',
    triggerData: 'Triggered by: SpO₂ reading of 93%',
    severity: 'warning',
  },
  {
    id: 'rec_3', timestamp: new Date(Date.now() - 26 * 3600 * 1000).toISOString(),
    type: 'activity',
    message: 'Great consistency yesterday — 9,400 steps! Keep it up with a short 10-minute walk after lunch to support digestion.',
    triggerData: 'Triggered by: daily step trend',
    severity: 'info',
  },
];

export const NIGERIAN_FOODS = [
  'Jollof Rice','Fried Rice','Ofada Rice','Pounded Yam','Eba','Amala','Fufu','Semovita',
  'Egusi Soup','Ogbono Soup','Efo Riro','Bitterleaf Soup','Okra Soup','Banga Soup',
  'Suya','Moi Moi','Akara','Pepper Soup','Nkwobi','Isi Ewu',
  'Grilled Chicken','Fried Plantain','Boiled Plantain','Yam Porridge','Beans Porridge',
  'Pap (Ogi)','Boiled Egg','Catfish Pepper Soup','Ewa Agoyin',
];

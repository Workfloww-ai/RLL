import { Company, Depot, TSM, Brand, DepotBrandSales, TsmBrandSales } from '../types';

export const HEADQUARTERS_LIST = [
  'All Headquarters',
  'Jaipur',
  'Jodhpur',
  'Udaipur',
  'Kota',
  'Sikar',
  'Alwar',
  'Sriganganagar',
  'Ajmer',
  'Bikaner',
];

export const STATES_LIST = ['Rajasthan'];

// Brands from Image 2
export const ALL_BRANDS_CATALOG = [
  { id: '100-pipers-blended-malt', name: '100 PIPERS BLENDED MALT' },
  { id: '100-pipers-blended-scotch', name: '100 PIPERS BLENDED SCOTCH' },
  { id: '100-pipers-exquisite-blend', name: '100 PIPERS EXQUISITE BLEND' },
  { id: '1800-anejo-tequila', name: '1800 Añejo Tequila' },
  { id: '1800-coconut-liqueur', name: '1800 COCONUT LIQUEUR' },
  { id: '1800-milenio-extra-anejo', name: '1800 Milenio Extra Anejo Tequila' },
  { id: '1800-reposado-tequila', name: '1800 REPOSADO TEQUILA' },
  { id: '1800-silver-tequila', name: '1800 Silver Tequila' },
  { id: '1965-spirit-of-victory', name: '1965 SPIRIT OF VICTORY RUM' },
  { id: '8-pm-premium-black', name: '8 PM PREMIUM BLACK EXQUISITE WHISKY' },
  { id: '8-pm-special-rare', name: '8 PM SPECIAL RARE WHISKY' },
  { id: 'aberfeldy-highland-malt', name: 'ABERFELDY HIGHLAND SINGLE MALT' },
  { id: 'aberlour-16-year-old', name: 'ABERLOUR 16 YEAR OLD HIGHLAND' },
  { id: 'aberlour-speyside-single', name: 'ABERLOUR SPEYSIDE SINGLE MALT' },
  { id: 'absente-49', name: 'ABSENTE 49' },
  { id: 'absolut-citron-lemon', name: 'ABSOLUT CITRON LEMON' },
  { id: 'absolut-grapefruit-vodka', name: 'ABSOLUT GRAPEFRUIT VODKA' },
  { id: 'absolut-lime-flavored', name: 'ABSOLUT LIME FLAVORED' },
  { id: 'absolut-mandrin-mandarin', name: 'ABSOLUT MANDRIN MANDARIN' },
  { id: 'absolut-vodka', name: 'ABSOLUT VODKA' },
  { id: 'absolut-vodka-raspberi', name: 'ABSOLUT VODKA RASPBERI' },
  { id: 'after-dark-blue-classic', name: 'AFTER DARK BLUE CLASSIC' },
  { id: 'ag-forty-seven-chardonnay', name: 'AG FORTY SEVEN CHARDONNAY' },
  { id: 'ag-forty-seven-malbec', name: 'AG FORTY SEVEN MALBEC' },
  { id: 'akori-gin-cherry-blossom', name: 'AKORI GIN CHERRY BLOSSOM' },
  { id: 'all-seasons-golden-collection', name: 'ALL SEASONS GOLDEN COLLECTION' },
];

// Helper to construct metrics
function createMetrics(dailyCases: number, dailyBottles: number) {
  const dailyBL = Number((dailyCases * 8.5).toFixed(1));
  return {
    Daily: { cases: dailyCases, bottles: dailyBottles, bl: dailyBL },
    MTD: { cases: dailyCases * 24, bottles: dailyBottles * 24, bl: Number((dailyBL * 24).toFixed(1)) },
    YTD: { cases: dailyCases * 270, bottles: dailyBottles * 270, bl: Number((dailyBL * 270).toFixed(1)) },
  };
}

// 12 Companies strictly matching Image 1
export const INITIAL_COMPANIES: Company[] = [
  {
    id: 'amrut',
    name: 'Amrut',
    isPinned: false,
    hqLocation: 'Udaipur',
    data: createMetrics(940, 4820),
    brands: [
      { id: 'amrut-fusion', name: 'Amrut Fusion Single Malt Whisky', data: createMetrics(520, 2600) },
      { id: 'amrut-amalgam', name: 'Amrut Amalgam Malt Whisky', data: createMetrics(420, 2220) },
    ],
  },
  {
    id: 'ardent',
    name: 'Ardent',
    isPinned: false,
    hqLocation: 'Jaipur',
    data: createMetrics(680, 3100),
    brands: [
      { id: '1800-anejo-tequila', name: '1800 Añejo Tequila', data: createMetrics(340, 1500) },
      { id: '1800-coconut-liqueur', name: '1800 COCONUT LIQUEUR', data: createMetrics(340, 1600) },
    ],
  },
  {
    id: 'beyond-water',
    name: 'Beyond Water',
    isPinned: false,
    hqLocation: 'Jodhpur',
    data: createMetrics(420, 2100),
    brands: [
      { id: 'ag-forty-seven-chardonnay', name: 'AG FORTY SEVEN CHARDONNAY', data: createMetrics(210, 1050) },
      { id: 'ag-forty-seven-malbec', name: 'AG FORTY SEVEN MALBEC', data: createMetrics(210, 1050) },
    ],
  },
  {
    id: 'campari',
    name: 'Campari',
    isPinned: false,
    hqLocation: 'Kota',
    data: createMetrics(820, 4900),
    brands: [
      { id: '1800-reposado-tequila', name: '1800 REPOSADO TEQUILA', data: createMetrics(410, 2450) },
      { id: '1800-silver-tequila', name: '1800 Silver Tequila', data: createMetrics(410, 2450) },
    ],
  },
  {
    id: 'diageo-inbrew',
    name: 'Diageo/In brew',
    isPinned: true,
    hqLocation: 'Jaipur',
    data: createMetrics(1420, 8900),
    brands: [
      { id: '100-pipers-blended-malt', name: '100 PIPERS BLENDED MALT', data: createMetrics(510, 3200) },
      { id: '100-pipers-blended-scotch', name: '100 PIPERS BLENDED SCOTCH', data: createMetrics(480, 2900) },
      { id: '100-pipers-exquisite-blend', name: '100 PIPERS EXQUISITE BLEND', data: createMetrics(430, 2800) },
    ],
  },
  {
    id: 'khoday',
    name: 'Khoday',
    isPinned: false,
    hqLocation: 'Sikar',
    data: createMetrics(510, 2400),
    brands: [
      { id: '1965-spirit-of-victory', name: '1965 SPIRIT OF VICTORY RUM', data: createMetrics(510, 2400) },
    ],
  },
  {
    id: 'kostroma-distillery',
    name: 'Kostroma Distillery (Russia)',
    isPinned: false,
    hqLocation: 'Alwar',
    data: createMetrics(620, 3400),
    brands: [
      { id: 'absolut-vodka', name: 'ABSOLUT VODKA', data: createMetrics(320, 1700) },
      { id: 'absolut-citron-lemon', name: 'ABSOLUT CITRON LEMON', data: createMetrics(300, 1700) },
    ],
  },
  {
    id: 'mhi',
    name: 'MHI',
    isPinned: false,
    hqLocation: 'Ajmer',
    data: createMetrics(730, 4200),
    brands: [
      { id: 'absolut-grapefruit-vodka', name: 'ABSOLUT GRAPEFRUIT VODKA', data: createMetrics(250, 1400) },
      { id: 'absolut-lime-flavored', name: 'ABSOLUT LIME FLAVORED', data: createMetrics(240, 1400) },
      { id: 'absolut-mandrin-mandarin', name: 'ABSOLUT MANDRIN MANDARIN', data: createMetrics(240, 1400) },
    ],
  },
  {
    id: 'others',
    name: 'Others',
    isPinned: false,
    hqLocation: 'Bikaner',
    data: createMetrics(380, 1900),
    brands: [
      { id: 'absente-49', name: 'ABSENTE 49', data: createMetrics(190, 950) },
      { id: 'akori-gin-cherry-blossom', name: 'AKORI GIN CHERRY BLOSSOM', data: createMetrics(190, 950) },
    ],
  },
  {
    id: 'rll',
    name: 'RLL',
    isPinned: true,
    hqLocation: 'Sriganganagar',
    data: createMetrics(890, 4700),
    brands: [
      { id: '8-pm-premium-black', name: '8 PM PREMIUM BLACK EXQUISITE WHISKY', data: createMetrics(450, 2400) },
      { id: '8-pm-special-rare', name: '8 PM SPECIAL RARE WHISKY', data: createMetrics(440, 2300) },
    ],
  },
  {
    id: 'sgs',
    name: 'SGS',
    isPinned: false,
    hqLocation: 'Jaipur',
    data: createMetrics(760, 3800),
    brands: [
      { id: 'after-dark-blue-classic', name: 'AFTER DARK BLUE CLASSIC', data: createMetrics(380, 1900) },
      { id: 'all-seasons-golden-collection', name: 'ALL SEASONS GOLDEN COLLECTION', data: createMetrics(380, 1900) },
    ],
  },
  {
    id: 'william-grants',
    name: 'William Grants',
    isPinned: false,
    hqLocation: 'Udaipur',
    data: createMetrics(910, 5200),
    brands: [
      { id: 'aberfeldy-highland-malt', name: 'ABERFELDY HIGHLAND SINGLE MALT', data: createMetrics(310, 1800) },
      { id: 'aberlour-16-year-old', name: 'ABERLOUR 16 YEAR OLD HIGHLAND', data: createMetrics(300, 1700) },
      { id: 'aberlour-speyside-single', name: 'ABERLOUR SPEYSIDE SINGLE MALT', data: createMetrics(300, 1700) },
    ],
  },
];

// Helper to create realistic depot brand sales
function createDepotBrandSales(multiplier: number): DepotBrandSales[] {
  return ALL_BRANDS_CATALOG.slice(0, 8).map((b) => {
    const baseCases = Math.round((Math.random() * 60 + 20) * multiplier);
    const baseBottles = Math.round(baseCases * (Math.floor(Math.random() * 6) + 4));
    const baseBL = Number((baseCases * 8.5).toFixed(1));

    return {
      brandId: b.id,
      brandName: b.name,
      data: {
        Daily: { cases: baseCases, bottles: baseBottles, bl: baseBL },
        MTD: { cases: baseCases * 24, bottles: baseBottles * 24, bl: Number((baseBL * 24).toFixed(1)) },
        YTD: { cases: baseCases * 270, bottles: baseBottles * 270, bl: Number((baseBL * 270).toFixed(1)) },
      },
    };
  });
}

// Depots List
export const INITIAL_DEPOTS: Depot[] = [
  {
    id: 'sikar-cwc',
    name: 'R.S.B.C.L. - Sikar Depot (CWC)',
    hqName: 'Sikar',
    address: 'CWC Warehousing Complex, Sikar',
    brands: createDepotBrandSales(1.2),
    data: { Daily: { cases: 0, bottles: 0, bl: 0 }, MTD: { cases: 0, bottles: 0, bl: 0 }, YTD: { cases: 0, bottles: 0, bl: 0 } },
  },
  {
    id: 'udaipur-transport-nagar',
    name: 'R.S.B.C.L. - Udaipur (Transport Nagar)',
    hqName: 'Udaipur',
    address: 'Transport Nagar Industrial Area, Udaipur',
    brands: createDepotBrandSales(1.4),
    data: { Daily: { cases: 0, bottles: 0, bl: 0 }, MTD: { cases: 0, bottles: 0, bl: 0 }, YTD: { cases: 0, bottles: 0, bl: 0 } },
  },
  {
    id: 'behror-depot',
    name: 'R.S.B.C.L. - Behror Depot',
    hqName: 'Alwar',
    address: 'RIICO Industrial Area, Behror',
    brands: createDepotBrandSales(1.1),
    data: { Daily: { cases: 0, bottles: 0, bl: 0 }, MTD: { cases: 0, bottles: 0, bl: 0 }, YTD: { cases: 0, bottles: 0, bl: 0 } },
  },
  {
    id: 'jaipur-goner-road',
    name: 'R.S.B.C.L. - Jaipur (Goner Road)',
    hqName: 'Jaipur',
    address: 'Goner Road Logistics Park, Jaipur',
    brands: createDepotBrandSales(1.8),
    data: { Daily: { cases: 0, bottles: 0, bl: 0 }, MTD: { cases: 0, bottles: 0, bl: 0 }, YTD: { cases: 0, bottles: 0, bl: 0 } },
  },
  {
    id: 'kota-cwc',
    name: 'R.S.B.C.L. - Kota ( CWC )',
    hqName: 'Kota',
    address: 'Central Warehousing Corporation, Kota',
    brands: createDepotBrandSales(1.5),
    data: { Daily: { cases: 0, bottles: 0, bl: 0 }, MTD: { cases: 0, bottles: 0, bl: 0 }, YTD: { cases: 0, bottles: 0, bl: 0 } },
  },
  {
    id: 'jodhpur-krishi-upaj-mandi',
    name: 'R.S.B.C.L. - Jodhpur krishi upaj mandi',
    hqName: 'Jodhpur',
    address: 'Krishi Upaj Mandi Complex, Mandore, Jodhpur',
    brands: createDepotBrandSales(1.6),
    data: { Daily: { cases: 0, bottles: 0, bl: 0 }, MTD: { cases: 0, bottles: 0, bl: 0 }, YTD: { cases: 0, bottles: 0, bl: 0 } },
  },
];

// Calculate aggregated depot data from brand sales
INITIAL_DEPOTS.forEach((depot) => {
  (['Daily', 'MTD', 'YTD'] as const).forEach((period) => {
    const totalCases = depot.brands.reduce((sum, b) => sum + b.data[period].cases, 0);
    const totalBottles = depot.brands.reduce((sum, b) => sum + b.data[period].bottles, 0);
    const totalBL = depot.brands.reduce((sum, b) => sum + b.data[period].bl, 0);
    depot.data[period] = {
      cases: totalCases,
      bottles: totalBottles,
      bl: Number(totalBL.toFixed(1)),
    };
  });
});

// Helper to create TSM Brand Sales
function createTsmBrandSales(multiplier: number): TsmBrandSales[] {
  return ALL_BRANDS_CATALOG.slice(0, 6).map((b) => {
    const baseCases = Math.round((Math.random() * 90 + 30) * multiplier);
    const baseBottles = Math.round(baseCases * (Math.floor(Math.random() * 8) + 4));
    const baseBL = Number((baseCases * 8.5).toFixed(1));

    return {
      brandId: b.id,
      brandName: b.name,
      data: {
        Daily: { cases: baseCases, bottles: baseBottles, bl: baseBL },
        MTD: { cases: baseCases * 24, bottles: baseBottles * 24, bl: Number((baseBL * 24).toFixed(1)) },
        YTD: { cases: baseCases * 270, bottles: baseBottles * 270, bl: Number((baseBL * 270).toFixed(1)) },
      },
    };
  });
}

// 8 TSMs strictly matching Image 3
export const INITIAL_TSMS: TSM[] = [
  { id: 'dharmendra-amlani', name: 'Dharmendra Amlani', hqLocation: 'Jaipur', brands: createTsmBrandSales(1.5), data: { Daily: { cases: 0, bottles: 0, bl: 0 }, MTD: { cases: 0, bottles: 0, bl: 0 }, YTD: { cases: 0, bottles: 0, bl: 0 } } },
  { id: 'manish-kumar', name: 'Manish Kumar', hqLocation: 'Udaipur', brands: createTsmBrandSales(1.3), data: { Daily: { cases: 0, bottles: 0, bl: 0 }, MTD: { cases: 0, bottles: 0, bl: 0 }, YTD: { cases: 0, bottles: 0, bl: 0 } } },
  { id: 'puneet-bhardwaj', name: 'Puneet Bhardwaj', hqLocation: 'Jodhpur', brands: createTsmBrandSales(1.4), data: { Daily: { cases: 0, bottles: 0, bl: 0 }, MTD: { cases: 0, bottles: 0, bl: 0 }, YTD: { cases: 0, bottles: 0, bl: 0 } } },
  { id: 'rajesh-dinbandhu', name: 'Rajesh Dinbandhu', hqLocation: 'Kota', brands: createTsmBrandSales(1.2), data: { Daily: { cases: 0, bottles: 0, bl: 0 }, MTD: { cases: 0, bottles: 0, bl: 0 }, YTD: { cases: 0, bottles: 0, bl: 0 } } },
  { id: 'ravi-tak', name: 'Ravi Tak', hqLocation: 'Sikar', brands: createTsmBrandSales(1.1), data: { Daily: { cases: 0, bottles: 0, bl: 0 }, MTD: { cases: 0, bottles: 0, bl: 0 }, YTD: { cases: 0, bottles: 0, bl: 0 } } },
  { id: 'rishabh-bhanot', name: 'Rishabh Bhanot', hqLocation: 'Alwar', brands: createTsmBrandSales(1.25), data: { Daily: { cases: 0, bottles: 0, bl: 0 }, MTD: { cases: 0, bottles: 0, bl: 0 }, YTD: { cases: 0, bottles: 0, bl: 0 } } },
  { id: 'vaibhav-soni', name: 'Vaibhav Soni', hqLocation: 'Ajmer', brands: createTsmBrandSales(1.0), data: { Daily: { cases: 0, bottles: 0, bl: 0 }, MTD: { cases: 0, bottles: 0, bl: 0 }, YTD: { cases: 0, bottles: 0, bl: 0 } } },
  { id: 'vishal-singh-chauhan', name: 'Vishal Singh Chauhan', hqLocation: 'Sriganganagar', brands: createTsmBrandSales(1.35), data: { Daily: { cases: 0, bottles: 0, bl: 0 }, MTD: { cases: 0, bottles: 0, bl: 0 }, YTD: { cases: 0, bottles: 0, bl: 0 } } },
];

// Calculate aggregated TSM data from brand sales
INITIAL_TSMS.forEach((tsm) => {
  (['Daily', 'MTD', 'YTD'] as const).forEach((period) => {
    const totalCases = tsm.brands.reduce((sum, b) => sum + b.data[period].cases, 0);
    const totalBottles = tsm.brands.reduce((sum, b) => sum + b.data[period].bottles, 0);
    const totalBL = tsm.brands.reduce((sum, b) => sum + b.data[period].bl, 0);
    tsm.data[period] = {
      cases: totalCases,
      bottles: totalBottles,
      bl: Number(totalBL.toFixed(1)),
    };
  });
});

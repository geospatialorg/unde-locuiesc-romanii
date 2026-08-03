import type { QueryState } from "./model";

/** O variantă rapidă a unei întrebări (ex. oraș ↔ sat), comutabilă când presetul e activ. */
export interface PresetVariant {
  label: string;
  definition: string;
  query: QueryState;
}

/** Un prag reglabil direct din panoul rezultatului (ex. distanța max. până la o arie protejată). */
export interface PresetThreshold {
  /** variabila (constrângere „between”) al cărei prag se editează */
  varId: string;
  /** care capăt al intervalului setează caseta */
  bound: "min" | "max";
  label: string;
  unit: string;
  /** valoarea implicită (trebuie să coincidă cu cea din `query`) */
  default: number;
  step?: number;
  minValue?: number;
  /** capătul superior inclusiv (≤): pragul 0 selectează celulele cu exact 0 */
  inclusive?: boolean;
}

export interface Preset {
  id: string;
  title: string;
  /** definiția afișată sub rezultat — contractul metodologic al presetului */
  definition: string;
  query: QueryState;
  /** variante comutabile (ex. „La oraș” / „La sat”); prima e cea implicită */
  variants?: PresetVariant[];
  /** casetă de prag reglabil, păstrează presetul activ la editare */
  threshold?: PresetThreshold;
}

/** Preseturile v0 — doar pe variabilele deja disponibile în date. */
export const PRESETS: Preset[] = [
  {
    id: "la-mare",
    title: "Câți români locuiesc la mare?",
    definition: "Definiție: la mai puțin de 5 km de linia țărmului Mării Negre (ajustabil din filtre).",
    query: {
      measure: "pop_total",
      constraints: [{ varId: "dist_coast_km", op: "between", min: null, max: 5 }],
    },
  },
  {
    id: "frontiera",
    title: "Câți români locuiesc în zona de frontieră?",
    definition: "Definiție: la mai puțin de 30 km de frontiera de stat terestră/fluvială (definiția legală a zonei de frontieră).",
    query: {
      measure: "pop_total",
      constraints: [{ varId: "dist_border_km", op: "between", min: null, max: 30 }],
    },
  },
  {
    id: "munte",
    title: "Câți români locuiesc la munte?",
    definition: "Definiție: zone de munte, după forma de relief.",
    query: {
      measure: "pop_total",
      constraints: [{ varId: "landform_type", op: "in", values: ["munte"] }],
    },
  },
  {
    id: "deal",
    title: "Câți români locuiesc la deal sau podiș?",
    definition: "Definiție: forme de relief de tip „deal”, „podiș” sau „depresiune”.",
    query: {
      measure: "pop_total",
      constraints: [{ varId: "landform_type", op: "in", values: ["deal", "podiș", "depresiune"] }],
    },
  },
  {
    id: "campie",
    title: "Câți români locuiesc la câmpie?",
    definition: "Definiție: forme de relief de tip „câmpie”, „vale”, „grind” sau „baltă/lac”.",
    query: {
      measure: "pop_total",
      constraints: [
        { varId: "landform_type", op: "in", values: ["câmpie", "vale", "grind", "baltă/lac"] },
      ],
    },
  },
  {
    id: "unitate-relief",
    title: "Câți români locuiesc într-o anumită unitate de relief?",
    definition:
      "Definiție: bifează una sau mai multe mari unități de relief (Carpați, Subcarpați, podișuri, dealuri, câmpii…) din filtrele de mai jos.",
    query: {
      measure: "pop_total",
      constraints: [{ varId: "landform_lvl0", op: "in", values: [] }],
    },
  },
  {
    id: "judet",
    title: "Câți români locuiesc într-un anumit județ?",
    definition: "Definiție: bifează unul sau mai multe județe din filtrele de mai jos.",
    query: {
      measure: "pop_total",
      constraints: [{ varId: "county_mn", op: "in", values: [] }],
    },
  },
  {
    id: "corp-apa",
    title: "Câți români locuiesc în apropierea unui lac?",
    definition:
      "Definiție: la mai puțin de 1 km de cel mai apropiat corp de apă — lac, lac de acumulare, iaz, baltă sau lagună. Distanța e ajustabilă, iar tipul apei se poate bifa din filtrele de mai jos.",
    query: {
      measure: "pop_total",
      constraints: [
        { varId: "dist_water_km", op: "between", min: null, max: 1 },
        { varId: "categorie_apa", op: "in", values: [] },
      ],
    },
  },
  {
    id: "curs-apa",
    title: "Câți români locuiesc în apropierea unui curs de apă?",
    definition:
      "Definiție: la mai puțin de 500 m de cel mai apropiat curs de apă — râu sau pârâu. Distanța e ajustabilă, iar tipul se poate bifa din filtrele de mai jos.",
    query: {
      measure: "pop_total",
      constraints: [
        { varId: "dist_curs_km", op: "between", min: null, max: 0.5 },
        { varId: "categorie_curs", op: "in", values: [] },
      ],
    },
  },
  {
    id: "risc-inundatii",
    title: "Câți români locuiesc într-o zonă cu risc de inundații sau în apropierea acesteia?",
    definition:
      "Definiție: locul se află la cel mult distanța aleasă mai jos de o zonă cu hazard de inundații. Scenariile sunt cumulative (imbricate): 0,1% (~1.000 ani) e cel mai extins și include zonele de 1% (~100 ani) și 10% (~10 ani); „combinat” = reuniunea tuturor. La 0 km sunt incluse toate locurile care ating zona.",
    query: {
      measure: "pop_total",
      constraints: [
        { varId: "dist_inundatii_km", op: "between", min: null, max: 0, maxInclusive: true },
        { varId: "scenariu_inundatii", op: "in", values: [] },
      ],
    },
    variants: [
      {
        label: "Combinat",
        definition: "Toate scenariile la un loc (reuniunea zonelor de 10%, 1% și 0,1%).",
        query: {
          measure: "pop_total",
          constraints: [
            { varId: "dist_inundatii_km", op: "between", min: null, max: 0, maxInclusive: true },
            { varId: "scenariu_inundatii", op: "in", values: [] },
          ],
        },
      },
      {
        label: "0,1% (~1.000 ani)",
        definition: "Zona inundabilă la un eveniment cu 0,1% probabilitate anuală (~1.000 ani) — cea mai extinsă; include 1% și 10%.",
        query: {
          measure: "pop_total",
          constraints: [
            { varId: "dist_inundatii_km", op: "between", min: null, max: 0, maxInclusive: true },
            { varId: "scenariu_inundatii", op: "in", values: ["0,1% (~1.000 ani)", "1% (~100 ani)", "10% (~10 ani)"] },
          ],
        },
      },
      {
        label: "1% (~100 ani)",
        definition: "Zona inundabilă la un eveniment cu 1% probabilitate anuală (~100 ani) — include și 10%.",
        query: {
          measure: "pop_total",
          constraints: [
            { varId: "dist_inundatii_km", op: "between", min: null, max: 0, maxInclusive: true },
            { varId: "scenariu_inundatii", op: "in", values: ["1% (~100 ani)", "10% (~10 ani)"] },
          ],
        },
      },
      {
        label: "10% (~10 ani)",
        definition: "Zona inundabilă la un eveniment cu 10% probabilitate anuală (~10 ani) — cea mai frecventă, cea mai restrânsă.",
        query: {
          measure: "pop_total",
          constraints: [
            { varId: "dist_inundatii_km", op: "between", min: null, max: 0, maxInclusive: true },
            { varId: "scenariu_inundatii", op: "in", values: ["10% (~10 ani)"] },
          ],
        },
      },
    ],
    threshold: {
      varId: "dist_inundatii_km",
      bound: "max",
      label: "Distanța maximă până la o zonă inundabilă",
      unit: "km",
      default: 0,
      step: 0.5,
      minValue: 0,
      inclusive: true,
    },
  },
  {
    id: "arie-protejata",
    title: "Câți români locuiesc într-o arie protejată sau proximitatea unei arii protejate?",
    definition:
      "Definiție: locul se află la cel mult distanța aleasă mai jos de o arie protejată — parc național, parc natural, rezervație naturală sau științifică, monument al naturii sau sit Natura 2000. La 0 km sunt incluse toate locurile care ating o arie protejată.",
    query: {
      measure: "pop_total",
      constraints: [{ varId: "dist_protected_km", op: "between", min: null, max: 0, maxInclusive: true }],
    },
    threshold: {
      varId: "dist_protected_km",
      bound: "max",
      label: "Distanța maximă până la o arie protejată",
      unit: "km",
      default: 0,
      step: 0.5,
      minValue: 0,
      inclusive: true,
    },
  },
  {
    id: "oras-sat",
    title: "Câți români locuiesc la oraș?",
    definition:
      "Definiție: în interiorul construit al unei localități urbane — oraș sau municipiu. Comută rapid la „sat” mai jos.",
    query: {
      measure: "pop_total",
      constraints: [{ varId: "intravilan", op: "in", values: ["oraș"] }],
    },
    variants: [
      {
        label: "La oraș",
        definition:
          "Definiție: în interiorul construit al unei localități urbane — oraș sau municipiu.",
        query: { measure: "pop_total", constraints: [{ varId: "intravilan", op: "in", values: ["oraș"] }] },
      },
      {
        label: "La sat",
        definition:
          "Definiție: în interiorul construit al unei localități rurale — sat.",
        query: { measure: "pop_total", constraints: [{ varId: "intravilan", op: "in", values: ["sat"] }] },
      },
    ],
  },
  {
    id: "acces-gaz",
    title: "Câți români locuiesc în zone deservite de rețeaua de distribuție a gazelor naturale?",
    definition:
      "Definiție: localitatea este branșată sau se poate branșa la rețeaua de gaze naturale.",
    query: {
      measure: "pop_total",
      constraints: [{ varId: "acces_gaz", op: "in", values: ["conectat"] }],
    },
  },
  {
    id: "departe-spital",
    title: "Câți români locuiesc departe de un spital?",
    definition:
      "Definiție: la cel puțin 10 km în linie dreaptă de cel mai apropiat spital. Apasă pe hartă pentru distanța și timpul real pe șosea.",
    query: {
      measure: "pop_total",
      constraints: [{ varId: "dist_hospital_km", op: "between", min: 10, max: null }],
    },
    variants: [
      {
        label: "≥ 10 km",
        definition:
          "Definiție: la cel puțin 10 km în linie dreaptă de cel mai apropiat spital. Apasă pe hartă pentru ruta reală.",
        query: {
          measure: "pop_total",
          constraints: [{ varId: "dist_hospital_km", op: "between", min: 10, max: null }],
        },
      },
      {
        label: "≥ 20 km",
        definition:
          "Definiție: la cel puțin 20 km în linie dreaptă de cel mai apropiat spital.",
        query: {
          measure: "pop_total",
          constraints: [{ varId: "dist_hospital_km", op: "between", min: 20, max: null }],
        },
      },
      {
        label: "≥ 25 km",
        definition:
          "Definiție: la cel puțin 25 km în linie dreaptă de cel mai apropiat spital.",
        query: {
          measure: "pop_total",
          constraints: [{ varId: "dist_hospital_km", op: "between", min: 25, max: null }],
        },
      },
    ],
  },
  {
    id: "peste-1000",
    title: "Câți români locuiesc la peste 1.000 m?",
    definition: "Definiție: altitudinea medie a locului depășește 1.000 m.",
    query: {
      measure: "pop_total",
      constraints: [{ varId: "alt_mean", op: "between", min: 1000, max: null }],
    },
  },
  {
    id: "exemplu-multi",
    title: "Exemplu multi-criteriu: femei, 200–500 m, climă anume",
    definition: "Definiție: femei, la altitudine medie de 200–500 m, cu precipitații de până la 400 mm și temperatură medie de 11,5–12,5 °C în anul curent.",
    query: {
      measure: "pop_f",
      constraints: [
        { varId: "alt_mean", op: "between", min: 200, max: 500 },
        { varId: "precip_total", op: "between", min: null, max: 400 },
        { varId: "tmean", op: "between", min: 11.5, max: 12.5 },
      ],
    },
  },
];

/** „Alte întrebări” — listă extinsă, ascunsă implicit; se va completa în timp. */
export const MORE_PRESETS: Preset[] = [
  {
    id: "bucuresti",
    title: "Câți români locuiesc în București?",
    definition: "Definiție: locurile din municipiul București.",
    query: { measure: "pop_total", constraints: [{ varId: "county_mn", op: "in", values: ["B"] }] },
  },
  {
    id: "altitudine-joasa",
    title: "Câți români locuiesc sub 100 m altitudine?",
    definition: "Definiție: altitudinea medie a locului este sub 100 m.",
    query: { measure: "pop_total", constraints: [{ varId: "alt_mean", op: "between", min: null, max: 100 }] },
  },
  {
    id: "departe-aeroport",
    title: "Câți români locuiesc departe de un aeroport?",
    definition:
      "Definiție: la cel puțin 50 km în linie dreaptă de cel mai apropiat aeroport. Apasă pe hartă pentru ruta reală pe șosea.",
    query: {
      measure: "pop_total",
      constraints: [{ varId: "dist_airport_km", op: "between", min: 50, max: null }],
    },
    variants: [
      { label: "≥ 50 km", definition: "Definiție: la cel puțin 50 km de cel mai apropiat aeroport.",
        query: { measure: "pop_total", constraints: [{ varId: "dist_airport_km", op: "between", min: 50, max: null }] } },
      { label: "≥ 75 km", definition: "Definiție: la cel puțin 75 km de cel mai apropiat aeroport.",
        query: { measure: "pop_total", constraints: [{ varId: "dist_airport_km", op: "between", min: 75, max: null }] } },
      { label: "≥ 100 km", definition: "Definiție: la cel puțin 100 km de cel mai apropiat aeroport.",
        query: { measure: "pop_total", constraints: [{ varId: "dist_airport_km", op: "between", min: 100, max: null }] } },
    ],
  },
  {
    id: "teren-inclinat",
    title: "Câți români locuiesc pe teren înclinat (pantă ≥ 5°)?",
    definition: "Definiție: panta medie a locului este de cel puțin 5°.",
    query: { measure: "pop_total", constraints: [{ varId: "slope_mean", op: "between", min: 5, max: null }] },
  },
  {
    id: "incalzire",
    title: "Câți români locuiesc în zone care s-au încălzit cu peste 1,1 °C?",
    definition:
      "Definiție: temperatura medie a ultimelor trei decenii (1991–2020) e cu cel puțin 1,1 °C mai caldă decât în perioada 1961–1990. La nivelul întregii țări, media este de aproximativ 1,0 °C.",
    query: {
      measure: "pop_total",
      constraints: [{ varId: "warming_deg", op: "between", min: 1.1, max: null }],
    },
  },
  {
    id: "zile-caniculare",
    title: "Câți români locuiesc în zone cu multe zile caniculare (≥ 20)?",
    definition: "Definiție: cel puțin 20 de zile cu maxima ≥ 30 °C în anul curent (actualizat zilnic).",
    query: { measure: "pop_total", constraints: [{ varId: "hot_days", op: "between", min: 20, max: null }] },
  },
];

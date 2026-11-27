export const techniques = {
    cromatico: ["Realce cromático", "Destaca diferenças cromáticas na superfície."],
    adaptativo: ["Realce adaptativo", "Adapta as cores à distribuição cromática da fotografia."],
    estrutural: ["Realce de estruturas", "Destaca contraste local de textura e formas superficiais."],
    combinado: ["Realce combinado", "Combina realce cromático e informações de estrutura."],
    blackhat: ["Estruturas escuras", "Resposta morfológica a regiões mais escuras que o entorno (Black Hat)."],
    tophat: ["Estruturas claras", "Resposta morfológica a regiões mais claras que o entorno (Top Hat)."],
    hessiana_escura: ["Realce de linhas escuras", "Resposta da Hessiana a estruturas lineares escuras."],
    hessiana_clara: ["Realce de linhas claras", "Resposta da Hessiana a estruturas lineares claras."],
    gabor: ["Texturas direcionais", "Resposta a orientações e frequências do banco de filtros Gabor."],
    suporte_estrutural: ["Mapa de estruturas", "Mapa da resposta conjunta do processamento estrutural."],
    roi: ["Área de análise", "Máscara que identifica a região utilizada no processamento."]
};

export const adjustments = {
    brightness: ["Brilho", 0, 3, 0.05],
    contrast: ["Contraste", 0, 3, 0.05],
    saturation: ["Saturação", 0, 3, 0.05],
    sharpness: ["Nitidez", 0, 3, 0.05],
    gamma: ["Gama", 0.1, 5, 0.05],
    channel: ["Canal RGB", 0, 2, 1],
    equalize: ["Equalização", 1, 1, 1],
    clahe: ["Contraste local", 1, 8, 1],
    decorrelation: ["Separação de cores", 1, 1, 1],
    pca: ["Componente principal", 0, 2, 1],
    hsv: ["Canal HSV", 0, 2, 1],
    lab: ["Canal Lab", 0, 2, 1]
};

export const neural = new Set(["adaptativo", "cromatico", "combinado"]);
export const intensity = new Set(["cromatico", "combinado"]);

export function techniqueName(key) {
    return techniques[key]?.[0] ?? (key === "original" ? "Original" : "Resultado");
}

export function element(name, text = "", attrs = {}) {
    const item = document.createElement(name);
    if (text) item.textContent = text;
    for (const [key, value] of Object.entries(attrs)) item.setAttribute(key, value);
    return item;
}

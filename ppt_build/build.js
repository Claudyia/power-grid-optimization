const pptxgen = require("pptxgenjs");

const NAVY = "0B3D59";
const NAVY_DARK = "082B40";
const TEAL = "1C7293";
const TEAL_LIGHT = "5FA8C7";
const GOLD = "FFB100";
const WHITE = "FFFFFF";
const INK = "20303D";
const MUTED = "6B7A85";
const CARD = "F1F5F8";
const CARD_BORDER = "DCE6EC";
const RED_SOFT = "C0433A";

const FONT_TITLE = "Cambria";
const FONT_BODY = "Calibri";

const W = 13.333;
const H = 7.5;
const MARGIN = 0.6;

const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE";

let slideCounter = 0;

const NOTES = {
  1: "Buongiorno a tutti. Il progetto che presento oggi è il Project 16 del corso di Innovazione e Trasformazione Digitale, modulo del professor Francesco Conte. Ho realizzato un sistema di controllo che gestisce ora per ora un impianto energetico industriale dotato di pannelli solari, pale eoliche, una batteria, un sistema a idrogeno e un collegamento alla rete elettrica. L'obiettivo è decidere continuamente come usare queste risorse per minimizzare i costi, rispettando tutti i vincoli tecnici dell'impianto.",
  2: "La presentazione è organizzata in sei parti. Partirò dal problema che dovevo risolvere, poi descriverò il sistema fisico dell'impianto. Spiegherò cos'è il controllo MPC, il tipo di controllo che ho usato per prendere le decisioni ora per ora. Dopodiché entrerò nel modello matematico che sta dietro ogni decisione, mostrerò come ho strutturato il codice, e concluderò con gli esperimenti che ho condotto e i risultati ottenuti, con numeri reali.",
  3: "Il problema di partenza è questo: abbiamo un impianto che produce energia da fonti rinnovabili, ha una batteria e un sistema a idrogeno per accumulare energia, ed è collegato alla rete elettrica per comprare o vendere energia quando serve. Ogni ora bisogna decidere come gestire tutte queste risorse insieme, rispettando quattro obiettivi principali dati dalla consegna del progetto: minimizzare il costo netto di mercato, soddisfare sempre il carico dell'edificio, che non è controllabile, mantenere la batteria sempre tra il 10 e il 90 per cento di carica, e minimizzare lo spreco di energia rinnovabile, quello che in gergo si chiama curtailment.",
  4: "Questo è lo schema dell'impianto. Al centro c'è un bus energetico, un punto virtuale dove tutta l'energia si incontra e deve bilanciarsi. Da un lato abbiamo le fonti rinnovabili, 4 megawatt di fotovoltaico e 8 di eolico. Dall'altro lato la rete elettrica, con cui possiamo importare fino a 12 megawatt o esportare fino a 10. In basso ci sono gli accumuli: una batteria da 1 megawatt e 1 megawattora, e un sistema a idrogeno da 20 megawattora, con un elettrolizzatore per produrlo e una fuel cell per riconvertirlo in energia. In alto c'è il carico dell'edificio, che dobbiamo sempre soddisfare e che non possiamo controllare.",
  5: "Tutti questi dati arrivano da tre file forniti con il progetto. Il primo contiene la produzione rinnovabile prevista e reale per ogni ora dell'anno. Il secondo contiene i consumi dell'edificio. Il terzo è il PUN, il prezzo unico nazionale, cioè il prezzo di mercato a cui possiamo vendere l'energia in eccesso. Il prezzo di acquisto invece non arriva da nessun file: segue una regola fissa con tre fasce orarie, che ho implementato direttamente nel codice.",
  6: "Il tipo di controllo che ho usato si chiama Model Predictive Control, o MPC. L'idea è questa: ogni ora, il sistema guarda le prossime 24 ore e calcola il piano ottimo per quel periodo, usando le previsioni disponibili in quel momento. È un po' come pianificare la settimana: siamo abbastanza sicuri di cosa succederà domani, ma il meteo di venerdì è solo una stima, e potrebbe cambiare.",
  7: "Una domanda che mi sono posto subito è: se calcoliamo un piano di 24 ore, perché non lo applichiamo tutto? La risposta è che le previsioni per le ore future possono sbagliare. Quindi applichiamo solo la prima decisione del piano, quella basata sul dato vero e non su una previsione. Poi aggiorniamo lo stato reale della batteria e dell'idrogeno, e ricalcoliamo tutto da capo per l'ora successiva, con dati più aggiornati. In questo modo il sistema si corregge continuamente, invece di seguire alla cieca un piano vecchio.",
  8: "Per calcolare il piano di ogni finestra di 24 ore, ho costruito un modello matematico di ottimizzazione con la libreria Pyomo, risolto poi con un solver, in questo caso Gurobi oppure HiGHS. Questo tipo di modello si chiama MILP, un problema lineare misto intero, e si compone di tre parti: le variabili, cioè cosa il modello può decidere; i vincoli, cioè le regole che non può violare; e la funzione obiettivo, cioè cosa deve minimizzare.",
  9: "Le variabili del modello si dividono in tre gruppi. Ci sono le potenze continue, come quanta energia importare, esportare, o quanta caricare e scaricare la batteria. Ci sono gli stati degli accumuli, cioè il livello di carica della batteria e quello dell'idrogeno. E infine ci sono delle variabili binarie, che funzionano come interruttori: valgono solo 0 o 1, e servono a impedire scelte contraddittorie, come comprare e vendere energia nella stessa ora.",
  10: "Il vincolo più importante del modello è il bilancio di potenza. In ogni singola ora, tutta l'energia che entra nel sistema, la rinnovabile non sprecata, quella comprata dalla rete, quella dalla fuel cell, la scarica della batteria, deve uguagliare esattamente tutta l'energia che esce: il carico dell'edificio, l'energia venduta, quella usata per produrre idrogeno, e quella per caricare la batteria. Questo vincolo vale per ognuna delle 24 ore della finestra, non solo per l'ora corrente.",
  11: "Batteria e sistema a idrogeno seguono la stessa logica. Il livello di ogni ora dipende da quello dell'ora precedente: se carico, il livello sale; se scarico, scende. In entrambi i casi ho tenuto conto dei rendimenti reali: la batteria ha un rendimento del 95 per cento sia in carica che in scarica, mentre l'idrogeno ha un rendimento del 73 per cento per l'elettrolizzatore e del 65 per cento per la fuel cell. E naturalmente elettrolizzatore e fuel cell non possono funzionare nella stessa ora.",
  12: "La funzione obiettivo è quella che il modello cerca di minimizzare: il costo netto di mercato, cioè quanto spendiamo per comprare energia meno quanto guadagniamo vendendola, più una penalità per ogni megawatt di rinnovabile sprecato. Questa penalità non è un costo reale di mercato, ma un numero che ho scelto io per orientare il comportamento del modello. Nello script principale l'ho impostata a 1000 euro per megawattora, un valore molto più alto dei prezzi normali, proprio per rendere lo spreco l'ultima opzione possibile. Ho anche creato una variante con questa penalità abbassata quasi a zero, per vedere cosa sarebbe cambiato: ne parlo più avanti nei risultati.",
  13: "Ecco come funziona in pratica il ciclo di simulazione, ora per ora. Prima si preparano i dati della finestra, con la previsione e il valore vero dell'ora corrente. Poi si risolve il modello MILP sulle 24 ore. Si applica solo la prima decisione. Si aggiorna lo stato reale di batteria e idrogeno. E infine si calcola il costo usando i dati veri, non le previsioni. Questo ciclo si ripete per ogni ora che vogliamo simulare, che sia una settimana o un anno intero.",
  14: "Dal punto di vista del codice, tutto parte dalla funzione main, che mette in fila i vari passi: legge gli argomenti da riga di comando, carica i dati con load_project_data, sceglie un solver disponibile con select_solver, esegue la simulazione ora per ora con run_mpc_simulation, che a sua volta chiama solve_mpc_step per ogni singola ora, e infine salva i risultati in un file CSV e crea un grafico riassuntivo. Ho anche creato una seconda versione dello script, es.py, identica in tutto tranne che per il valore della penalità sul curtailment.",
  15: "Per capire davvero come si comporta il sistema, non mi sono fermato a una singola simulazione. Ho ripetuto la simulazione sull'intero anno, quindi più di 6500 ore, in quattro scenari diversi: uno di base con gli accumuli a metà carica, uno con gli accumuli completamente vuoti, uno con gli accumuli completamente pieni, e uno identico al terzo ma con la penalità sul curtailment abbassata quasi a zero. Ho ripetuto ognuno di questi quattro scenari sia con il solver Gurobi che con il solver open source HiGHS, per un totale di otto simulazioni complete sull'anno.",
  16: "Questo è il risultato di uno di questi esperimenti, lo scenario di base risolto con Gurobi. Il grafico ha quattro pannelli: in alto la produzione rinnovabile confrontata con il carico e con il curtailment, che resta praticamente sempre a zero; poi gli scambi controllati con rete, batteria e idrogeno; poi il livello degli accumuli, che si mantiene sempre dentro i limiti imposti; e infine il costo cumulativo di mercato, che cresce in modo quasi lineare durante l'anno.",
  17: "I grafici, oltre a dirci che i vincoli sono rispettati, raccontano come si comporta il sistema, e ci sono tre cose che vale la pena far notare. La prima: l'impianto compra quasi sempre energia dalla rete. Nel pannello degli scambi domina l'importazione, perché la produzione rinnovabile da sola non basta quasi mai a coprire il carico, e infatti il costo cumulativo cresce sempre: l'impianto è nel complesso un compratore netto di energia. La seconda: la batteria lavora quasi sempre attaccata a uno dei due limiti, il 10 o il 90 per cento, e salta di continuo da un estremo all'altro. È troppo piccola, un solo megawattora contro flussi da diversi megawatt, per spostare davvero energia da un'ora costosa a una economica: di fatto serve solo da cuscinetto per chiudere il bilancio orario. La terza, la più curiosa: il sistema a idrogeno si svuota nei primi giorni e poi resta fermo a zero per tutto il resto dell'anno. Con rendimenti del 73 e del 65 per cento e una potenza minima di un megawatt, in questo scenario di prezzi non conviene mai metterlo in funzione.",
  18: "Questo è lo zoom sulla prima settimana del livello dei due accumuli. La linea della batteria, in blu, rimbalza di continuo tra il 10 e il 90 per cento: non esce mai dalla fascia ammessa, quindi il vincolo è sempre rispettato, ma si vede che viene usata al massimo delle sue possibilità, che però sono poche. La linea dell'idrogeno, in arancione, parte dal 50 per cento, viene consumata nei primi giorni e poi resta incollata a zero. Questo spiega anche perché le condizioni iniziali contano così poco: qualunque sia il punto di partenza, dopo poche ore la batteria è tornata ai suoi limiti e l'idrogeno si è svuotato, e il sistema di fatto dimentica da dove è partito.",
  19: "Mettendo a confronto tutti gli otto risultati emergono due cose interessanti. Primo: il costo cambia pochissimo tra i quattro scenari, meno dello 0,1 per cento, segno che le condizioni iniziali di batteria e idrogeno contano poco su un anno intero, come si vedeva anche dal grafico degli accumuli. Secondo: la differenza tra Gurobi e HiGHS è minima, meno dello 0,01 per cento: per questo modello il solver gratuito HiGHS è più che sufficiente, senza bisogno di una licenza commerciale.",
  20: "C'è un risultato che non mi aspettavo. Nello scenario D avevo abbassato la penalità sul curtailment quasi a zero, aspettandomi che il sistema sprecasse più energia rinnovabile. Invece il curtailment è rimasto a zero anche in questo caso, per tutto l'anno. Il motivo è soprattutto l'export verso la rete: visto che l'idrogeno resta fermo e la batteria è minuscola, è la vendita in rete a fare da valvola di sfogo per gli eccessi di rinnovabile, e con il limite di 10 megawatt in esportazione lo spazio è sempre sufficiente, anche quando gli accumuli partono già pieni. Ho osservato un vero caso di curtailment solo in un test sintetico che ho costruito apposta, con accumuli pieni e una produzione rinnovabile molto più alta del carico: in quel caso il modello ha sprecato esattamente i 3 megawatt che avevo calcolato a mano, confermando che il modello si comporta correttamente.",
  21: "Per concludere: il modello rispetta sempre il bilancio di potenza e tutti i vincoli tecnici di batteria e idrogeno. I risultati sono praticamente identici tra il solver commerciale e quello open source, quindi non è necessario un solver a pagamento per questo tipo di problema. E il sistema riesce sempre a evitare lo spreco di rinnovabile in tutti gli scenari annuali testati, appoggiandosi soprattutto alla rete: l'impianto è di fatto un compratore netto di energia, la batteria fa solo da cuscinetto e il sistema a idrogeno, con questi prezzi, resta quasi sempre fermo. Ci sono anche dei limiti: la penalità sul curtailment e gli stati iniziali sono scelte di modellazione mie, non specificate dalla consegna, e il caso di spreco reale l'ho osservato solo in un test sintetico. Uno sviluppo futuro interessante potrebbe essere testare condizioni meteo estreme, per capire quando il curtailment diventa davvero necessario anche su dati reali.",
  22: "Vi ringrazio per l'attenzione. Sono a disposizione per qualsiasi domanda sul modello, sul codice o sui risultati.",
};

function footer(slide, label) {
  slide.addText(label || "Project 16 — Controllo MPC di un sistema energetico industriale", {
    x: MARGIN, y: H - 0.42, w: 8, h: 0.3,
    fontFace: FONT_BODY, fontSize: 9, color: MUTED, align: "left", margin: 0,
  });
  slideCounter += 1;
  slide.addText(String(slideCounter), {
    x: W - MARGIN - 0.6, y: H - 0.42, w: 0.6, h: 0.3,
    fontFace: FONT_BODY, fontSize: 9, color: MUTED, align: "right", margin: 0,
  });
}

function contentHeader(slide, kicker, title, opts) {
  opts = opts || {};
  slide.addText(kicker.toUpperCase(), {
    x: MARGIN, y: 0.45, w: W - 2 * MARGIN, h: 0.35,
    fontFace: FONT_BODY, fontSize: 13, color: TEAL, bold: true,
    charSpacing: 2, margin: 0,
  });
  slide.addText(title, {
    x: MARGIN, y: 0.78, w: W - 2 * MARGIN, h: opts.titleH || 0.85,
    fontFace: FONT_TITLE, fontSize: opts.titleSize || 30, color: NAVY, bold: true, margin: 0,
  });
}

function circleLabel(slide, cx, cy, d, fill, label, labelColor, fontSize) {
  slide.addShape(pres.ShapeType.ellipse, {
    x: cx - d / 2, y: cy - d / 2, w: d, h: d,
    fill: { color: fill }, line: { type: "none" },
  });
  slide.addText(label, {
    x: cx - d / 2, y: cy - d / 2, w: d, h: d,
    fontFace: FONT_BODY, fontSize: fontSize || 13, color: labelColor || WHITE, bold: true,
    align: "center", valign: "middle", margin: 0,
  });
}

function card(slide, x, y, w, h, opts) {
  opts = opts || {};
  slide.addShape(pres.ShapeType.roundRect, {
    x, y, w, h, rectRadius: 0.08,
    fill: { color: opts.fill || CARD },
    line: { color: opts.line || CARD_BORDER, width: 1 },
    shadow: opts.shadow === false ? undefined : {
      type: "outer", color: "9AA7AF", opacity: 0.25, blur: 6, offset: 2, angle: 90,
    },
  });
}

// ---------------------------------------------------------------------------
// Slide 1 — Title
// ---------------------------------------------------------------------------
{
  const s = pres.addSlide();
  s.background = { color: NAVY };

  s.addShape(pres.ShapeType.ellipse, {
    x: W - 3.6, y: -1.6, w: 5.2, h: 5.2,
    fill: { color: NAVY_DARK }, line: { type: "none" },
  });
  s.addShape(pres.ShapeType.ellipse, {
    x: W - 2.1, y: 4.4, w: 3.2, h: 3.2,
    fill: { color: TEAL }, line: { type: "none" }, shadow: undefined,
  });

  circleLabel(s, 1.35, 1.35, 0.9, GOLD, "P16", NAVY_DARK, 17);

  s.addText("PROJECT 16 — INNOVAZIONE E TRASFORMAZIONE DIGITALE", {
    x: MARGIN, y: 2.55, w: 10.5, h: 0.4,
    fontFace: FONT_BODY, fontSize: 14, color: GOLD, bold: true, charSpacing: 2, margin: 0,
  });
  s.addText("Controllo MPC di un sistema\nenergetico industriale", {
    x: MARGIN, y: 3.0, w: 10.6, h: 1.9,
    fontFace: FONT_TITLE, fontSize: 42, color: WHITE, bold: true, margin: 0, lineSpacingMultiple: 1.05,
  });
  s.addText("Rinnovabili, batteria e idrogeno gestiti ora per ora con un modello\ndi ottimizzazione (MILP) risolto con Pyomo", {
    x: MARGIN, y: 5.0, w: 10, h: 0.8,
    fontFace: FONT_BODY, fontSize: 16, color: "CADCE8", margin: 0, lineSpacingMultiple: 1.2,
  });
  s.addText("Corso di Innovazione e Trasformazione Digitale, Modulo 2 — Prof. Francesco Conte (UCBM)", {
    x: MARGIN, y: 6.65, w: 11, h: 0.4,
    fontFace: FONT_BODY, fontSize: 12, color: TEAL_LIGHT, margin: 0,
  });
  s.addNotes(NOTES[1]);
}

// ---------------------------------------------------------------------------
// Slide 2 — Agenda
// ---------------------------------------------------------------------------
{
  const s = pres.addSlide();
  s.background = { color: WHITE };
  contentHeader(s, "Indice", "Come è organizzata questa presentazione");

  const items = [
    ["01", "Il problema", "Cosa deve fare il sistema e perché"],
    ["02", "Il sistema fisico", "Rinnovabili, batteria, idrogeno, rete"],
    ["03", "Il controllo MPC", "Come si decide ora per ora"],
    ["04", "Il modello matematico", "Variabili, vincoli, obiettivo"],
    ["05", "Il codice", "Come è organizzato lo script"],
    ["06", "Esperimenti e risultati", "Cosa succede in pratica, con numeri veri"],
  ];
  const colW = (W - 2 * MARGIN - 0.6) / 2;
  const rowH = 1.35;
  items.forEach((item, i) => {
    const col = i % 2;
    const row = Math.floor(i / 2);
    const x = MARGIN + col * (colW + 0.6);
    const y = 2.05 + row * (rowH + 0.25);
    card(s, x, y, colW, rowH);
    s.addText(item[0], {
      x: x + 0.25, y: y + 0.18, w: 1.0, h: 1.0,
      fontFace: FONT_TITLE, fontSize: 30, color: GOLD, bold: true, margin: 0,
    });
    s.addText(item[1], {
      x: x + 1.15, y: y + 0.2, w: colW - 1.35, h: 0.4,
      fontFace: FONT_BODY, fontSize: 15, color: NAVY, bold: true, margin: 0,
    });
    s.addText(item[2], {
      x: x + 1.15, y: y + 0.62, w: colW - 1.35, h: 0.65,
      fontFace: FONT_BODY, fontSize: 11.5, color: MUTED, margin: 0, lineSpacingMultiple: 1.15,
    });
  });
  s.addNotes(NOTES[2]);
  footer(s);
}

// ---------------------------------------------------------------------------
// Slide 3 — Il problema
// ---------------------------------------------------------------------------
{
  const s = pres.addSlide();
  s.background = { color: WHITE };
  contentHeader(s, "01 · Il problema", "Gestire un impianto energetico\nsenza sprecare né soldi né energia", { titleH: 1.3, titleSize: 28 });

  const bodyY = 2.55;
  s.addText(
    [
      { text: "Un impianto industriale produce energia da fonte rinnovabile, ha una batteria e un sistema a idrogeno, ed è collegato alla rete elettrica.", options: { bullet: true, breakLine: true } },
      { text: "Ogni ora bisogna decidere: quanta energia comprare o vendere, quanto caricare la batteria, quanto produrre o consumare idrogeno.", options: { bullet: true, breakLine: true } },
      { text: "L'obiettivo è minimizzare il costo, senza mai lasciare l'edificio senza energia e sprecando il meno possibile la produzione rinnovabile.", options: { bullet: true, breakLine: false } },
    ],
    {
      x: MARGIN, y: bodyY, w: 6.6, h: 3.6,
      fontFace: FONT_BODY, fontSize: 16, color: INK, paraSpaceAfter: 14, lineSpacingMultiple: 1.25,
    }
  );

  card(s, 8.0, bodyY, 4.7, 3.9, { fill: NAVY, line: NAVY, shadow: false });
  s.addText("4 OBIETTIVI DA RISPETTARE\nOGNI ORA", {
    x: 8.35, y: bodyY + 0.3, w: 4.0, h: 0.6,
    fontFace: FONT_BODY, fontSize: 12.5, color: GOLD, bold: true, charSpacing: 1, margin: 0,
  });
  const goals = [
    "a) Minimizzare il costo netto di mercato",
    "b) Soddisfare sempre il carico dell'edificio",
    "c) Batteria sempre tra il 10% e il 90%",
    "d) Minimizzare lo spreco di rinnovabile",
  ];
  goals.forEach((g, i) => {
    const gy = bodyY + 1.05 + i * 0.68;
    circleLabel(s, 8.75, gy + 0.18, 0.42, GOLD, String.fromCharCode(97 + i), NAVY_DARK, 14);
    s.addText(g.slice(3), {
      x: 9.15, y: gy - 0.02, w: 3.35, h: 0.55,
      fontFace: FONT_BODY, fontSize: 13, color: WHITE, valign: "middle", margin: 0, lineSpacingMultiple: 1.1,
    });
  });
  s.addNotes(NOTES[3]);
  footer(s);
}

// ---------------------------------------------------------------------------
// Slide 4 — Il sistema fisico (schema impianto)
// ---------------------------------------------------------------------------
{
  const s = pres.addSlide();
  s.background = { color: WHITE };
  contentHeader(s, "02 · Il sistema fisico", "Come è fatto l'impianto");

  const boxW = 2.55, boxH = 1.15;
  const midY = 3.55;
  const nodes = {
    res: { x: 0.75, y: midY, label: "RINNOVABILI", sub: "PV 4 MW + Eolico 8 MW", color: "2F8F4E" },
    bus: { x: (W - boxW) / 2, y: midY, label: "BUS ENERGETICO", sub: "Bilancio di potenza", color: NAVY },
    grid: { x: W - boxW - 0.75, y: midY, label: "RETE ELETTRICA", sub: "Import 12 MW / Export 10 MW", color: TEAL },
    bat: { x: (W - boxW) / 2 - 3.1, y: midY + 1.9, label: "BATTERIA", sub: "1 MW / 1 MWh, η 0.95", color: "8A5CBF" },
    h2: { x: (W - boxW) / 2 + 3.1, y: midY + 1.9, label: "SISTEMA A IDROGENO", sub: "20 MWh, elettrolizz. + fuel cell", color: "C0433A" },
    load: { x: (W - boxW) / 2, y: midY - 1.9, label: "CARICO EDIFICIO", sub: "Consumo non controllabile", color: MUTED },
  };

  function box(n) {
    s.addShape(pres.ShapeType.roundRect, {
      x: n.x, y: n.y, w: boxW, h: boxH, rectRadius: 0.09,
      fill: { color: n.color }, line: { type: "none" },
      shadow: { type: "outer", color: "9AA7AF", opacity: 0.3, blur: 5, offset: 2, angle: 90 },
    });
    s.addText(n.label, {
      x: n.x + 0.1, y: n.y + 0.14, w: boxW - 0.2, h: 0.4,
      fontFace: FONT_BODY, fontSize: 13, color: WHITE, bold: true, align: "center", margin: 0,
    });
    s.addText(n.sub, {
      x: n.x + 0.1, y: n.y + 0.58, w: boxW - 0.2, h: 0.5,
      fontFace: FONT_BODY, fontSize: 10.5, color: "EAF0F3", align: "center", margin: 0, lineSpacingMultiple: 1.05,
    });
  }

  function connector(x1, y1, x2, y2) {
    s.addShape(pres.ShapeType.line, {
      x: Math.min(x1, x2), y: Math.min(y1, y2),
      w: Math.abs(x2 - x1) || 0.01, h: Math.abs(y2 - y1) || 0.01,
      line: { color: "AEB9C2", width: 2 },
      flipH: x2 < x1, flipV: y2 < y1,
    });
  }

  const busCX = nodes.bus.x + boxW / 2;
  const busCY = nodes.bus.y + boxH / 2;
  connector(nodes.res.x + boxW, nodes.res.y + boxH / 2, nodes.bus.x, busCY);
  connector(nodes.bus.x + boxW, busCY, nodes.grid.x, nodes.grid.y + boxH / 2);
  connector(busCX, nodes.bus.y, busCX, nodes.load.y + boxH);
  connector(nodes.bat.x + boxW / 2, nodes.bat.y, busCX - 0.5, nodes.bus.y + boxH);
  connector(nodes.h2.x + boxW / 2, nodes.h2.y, busCX + 0.5, nodes.bus.y + boxH);

  box(nodes.res); box(nodes.bus); box(nodes.grid); box(nodes.bat); box(nodes.h2); box(nodes.load);

  s.addText("Ogni ora il bus energetico deve bilanciarsi: tutto ciò che entra (rinnovabile, import, scarica batteria, fuel cell) deve uguagliare tutto ciò che esce (carico, export, carica batteria, elettrolizzatore).", {
    x: MARGIN, y: H - 1.15, w: W - 2 * MARGIN, h: 0.6,
    fontFace: FONT_BODY, fontSize: 12.5, color: MUTED, italic: true, align: "center", margin: 0, lineSpacingMultiple: 1.15,
  });
  s.addNotes(NOTES[4]);
  footer(s);
}

// ---------------------------------------------------------------------------
// Slide 5 — Da dove vengono i dati
// ---------------------------------------------------------------------------
{
  const s = pres.addSlide();
  s.background = { color: WHITE };
  contentHeader(s, "02 · Il sistema fisico", "Da dove vengono i dati");

  const datasets = [
    { file: "res_1_year_pu.mat", label: "Rinnovabile", desc: "Produzione fotovoltaica ed eolica, un anno intero ora per ora, in valori per unità (0-1) della potenza nominale.", color: "2F8F4E" },
    { file: "buildings_load.mat", label: "Carico", desc: "Consumi dell'edificio ora per ora, in energia oraria (kWh), convertiti in potenza media (MW).", color: MUTED },
    { file: "PUN_2022.mat", label: "Prezzo di vendita", desc: "Prezzo unico nazionale dell'energia, un valore di mercato reale per ogni ora dell'anno.", color: TEAL },
  ];
  const cardW = (W - 2 * MARGIN - 2 * 0.5) / 3;
  datasets.forEach((d, i) => {
    const x = MARGIN + i * (cardW + 0.5);
    const y = 2.15;
    const h = 3.9;
    card(s, x, y, cardW, h);
    s.addShape(pres.ShapeType.roundRect, {
      x, y, w: cardW, h: 0.14, rectRadius: 0,
      fill: { color: d.color }, line: { type: "none" }, shadow: undefined,
    });
    s.addText(d.label.toUpperCase(), {
      x: x + 0.3, y: y + 0.4, w: cardW - 0.6, h: 0.4,
      fontFace: FONT_BODY, fontSize: 13, color: d.color, bold: true, charSpacing: 1, margin: 0,
    });
    s.addText(d.file, {
      x: x + 0.3, y: y + 0.8, w: cardW - 0.6, h: 0.5,
      fontFace: "Courier New", fontSize: 13, color: NAVY, bold: true, margin: 0,
    });
    s.addText(d.desc, {
      x: x + 0.3, y: y + 1.45, w: cardW - 0.6, h: 2.3,
      fontFace: FONT_BODY, fontSize: 12.5, color: INK, margin: 0, lineSpacingMultiple: 1.25,
    });
  });

  s.addText("Il prezzo di acquisto invece non arriva da un file: segue una regola fissa a tre fasce orarie (F1 punta, F2 intermedia, F3 fuori punta), definita nel codice.", {
    x: MARGIN, y: 6.3, w: W - 2 * MARGIN, h: 0.6,
    fontFace: FONT_BODY, fontSize: 12.5, color: MUTED, italic: true, align: "center", margin: 0, lineSpacingMultiple: 1.15,
  });
  s.addNotes(NOTES[5]);
  footer(s);
}

// ---------------------------------------------------------------------------
// Slide 6 — Cos'è il controllo MPC
// ---------------------------------------------------------------------------
{
  const s = pres.addSlide();
  s.background = { color: WHITE };
  contentHeader(s, "03 · Il controllo MPC", "Decidere guardando avanti, un'ora alla volta");

  s.addText(
    [
      { text: "Model Predictive Control: ad ogni ora, il sistema guarda le prossime 24 ore e calcola il piano migliore per quel periodo.", options: { bullet: true, breakLine: true } },
      { text: "Il piano usa le previsioni per le ore future, perché quelle ore non sono ancora successe e il valore vero non si conosce.", options: { bullet: true, breakLine: true } },
      { text: "È come pianificare la settimana sapendo che il meteo di domani è quasi certo, ma quello di venerdì è solo una stima.", options: { bullet: true, breakLine: false } },
    ],
    {
      x: MARGIN, y: 2.05, w: W - 2 * MARGIN, h: 2.0,
      fontFace: FONT_BODY, fontSize: 16, color: INK, paraSpaceAfter: 12, lineSpacingMultiple: 1.25,
    }
  );

  // Timeline diagram: 24 small boxes representing the rolling window
  const tlY = 4.35;
  const boxW = 0.42, gap = 0.06;
  const n = 18;
  const totalW = n * boxW + (n - 1) * gap;
  const startX = (W - totalW) / 2;
  for (let i = 0; i < n; i++) {
    const x = startX + i * (boxW + gap);
    s.addShape(pres.ShapeType.roundRect, {
      x, y: tlY, w: boxW, h: 0.55, rectRadius: 0.04,
      fill: { color: i === 0 ? GOLD : TEAL_LIGHT },
      line: { type: "none" },
    });
  }
  s.addText("ora corrente\n(dato vero)", {
    x: startX - 0.6, y: tlY + 0.62, w: 1.7, h: 0.5,
    fontFace: FONT_BODY, fontSize: 10.5, color: NAVY, bold: true, align: "left", margin: 0, lineSpacingMultiple: 1.0,
  });
  s.addText("prossime 23 ore della finestra (previsione)", {
    x: startX + boxW + gap, y: tlY + 0.62, w: totalW, h: 0.4,
    fontFace: FONT_BODY, fontSize: 10.5, color: MUTED, align: "left", margin: 0,
  });
  s.addText("finestra di 24 ore ricalcolata ad ogni passo →", {
    x: startX, y: tlY - 0.42, w: totalW, h: 0.35,
    fontFace: FONT_BODY, fontSize: 11.5, color: NAVY, bold: true, margin: 0,
  });

  s.addNotes(NOTES[6]);
  footer(s);
}

// ---------------------------------------------------------------------------
// Slide 7 — Perché solo la prima ora
// ---------------------------------------------------------------------------
{
  const s = pres.addSlide();
  s.background = { color: NAVY };
  contentHeader = contentHeader; // no-op reference kept for clarity
  s.addText("03 · IL CONTROLLO MPC", {
    x: MARGIN, y: 0.45, w: W - 2 * MARGIN, h: 0.35,
    fontFace: FONT_BODY, fontSize: 13, color: GOLD, bold: true, charSpacing: 2, margin: 0,
  });
  s.addText("Perché si applica solo la prima decisione?", {
    x: MARGIN, y: 0.78, w: W - 2 * MARGIN, h: 0.85,
    fontFace: FONT_TITLE, fontSize: 30, color: WHITE, bold: true, margin: 0,
  });

  const steps = [
    { n: "1", t: "Si calcola il piano ottimo per 24 ore", d: "usando le previsioni disponibili in quel momento" },
    { n: "2", t: "Si applica solo la decisione della 1ª ora", d: "quella per cui, per costruzione, si usa il dato vero" },
    { n: "3", t: "Si aggiorna lo stato reale", d: "il nuovo livello di batteria e idrogeno diventa il punto di partenza" },
    { n: "4", t: "Si ricalcola tutto per l'ora successiva", d: "con dati più aggiornati, invece di seguire un piano vecchio" },
  ];
  const stepW = (W - 2 * MARGIN - 3 * 0.4) / 4;
  steps.forEach((st, i) => {
    const x = MARGIN + i * (stepW + 0.4);
    const y = 2.3;
    card(s, x, y, stepW, 3.6, { fill: NAVY_DARK, line: NAVY_DARK, shadow: false });
    circleLabel(s, x + stepW / 2, y + 0.65, 0.7, GOLD, st.n, NAVY_DARK, 20);
    s.addText(st.t, {
      x: x + 0.25, y: y + 1.3, w: stepW - 0.5, h: 0.9,
      fontFace: FONT_BODY, fontSize: 14, color: WHITE, bold: true, align: "center", margin: 0, lineSpacingMultiple: 1.15,
    });
    s.addText(st.d, {
      x: x + 0.25, y: y + 2.25, w: stepW - 0.5, h: 1.2,
      fontFace: FONT_BODY, fontSize: 11.5, color: "B9C9D4", align: "center", margin: 0, lineSpacingMultiple: 1.2,
    });
    if (i < steps.length - 1) {
      s.addText("→", {
        x: x + stepW, y: y + 1.4, w: 0.4, h: 0.5,
        fontFace: FONT_BODY, fontSize: 22, color: GOLD, align: "center", valign: "middle", margin: 0,
      });
    }
  });

  s.addText("Così il sistema si corregge continuamente, invece di seguire alla cieca un piano lungo basato su previsioni ormai superate.", {
    x: MARGIN, y: 6.3, w: W - 2 * MARGIN, h: 0.5,
    fontFace: FONT_BODY, fontSize: 13, color: "CADCE8", italic: true, align: "center", margin: 0,
  });
  s.addNotes(NOTES[7]);
  footer(s, "Project 16 — Controllo MPC di un sistema energetico industriale");
}

// ---------------------------------------------------------------------------
// Slide 8 — MILP: le tre parti del modello
// ---------------------------------------------------------------------------
{
  const s = pres.addSlide();
  s.background = { color: WHITE };
  contentHeader(s, "04 · Il modello matematico", "Un problema di ottimizzazione: il MILP");

  s.addText("Ad ogni ora, per calcolare la finestra di 24 ore, si costruisce un modello matematico con Pyomo e lo si risolve con un solver (Gurobi o HiGHS). Il modello ha tre parti:", {
    x: MARGIN, y: 2.0, w: W - 2 * MARGIN, h: 0.75,
    fontFace: FONT_BODY, fontSize: 15.5, color: INK, lineSpacingMultiple: 1.2, margin: 0,
  });

  const parts = [
    { label: "VARIABILI", title: "Cosa può decidere il modello", desc: "Quanta energia importare, esportare, caricare o scaricare, produrre o consumare come idrogeno, ora per ora.", color: TEAL },
    { label: "VINCOLI", title: "Cosa non può violare", desc: "Il bilancio di potenza, i limiti di rete, batteria e idrogeno, gli stati minimi e massimi ammessi.", color: NAVY },
    { label: "OBIETTIVO", title: "Cosa deve minimizzare", desc: "Il costo netto di mercato, più una penalità per ogni MW di rinnovabile sprecato.", color: RED_SOFT },
  ];
  const cardW = (W - 2 * MARGIN - 2 * 0.5) / 3;
  parts.forEach((p, i) => {
    const x = MARGIN + i * (cardW + 0.5);
    const y = 3.0;
    const h = 3.1;
    card(s, x, y, cardW, h, { fill: p.color, line: p.color, shadow: false });
    s.addText(p.label, {
      x: x + 0.3, y: y + 0.3, w: cardW - 0.6, h: 0.4,
      fontFace: FONT_BODY, fontSize: 12.5, color: GOLD, bold: true, charSpacing: 1.5, margin: 0,
    });
    s.addText(p.title, {
      x: x + 0.3, y: y + 0.75, w: cardW - 0.6, h: 0.85,
      fontFace: FONT_TITLE, fontSize: 17, color: WHITE, bold: true, margin: 0, lineSpacingMultiple: 1.1,
    });
    s.addText(p.desc, {
      x: x + 0.3, y: y + 1.65, w: cardW - 0.6, h: 1.35,
      fontFace: FONT_BODY, fontSize: 12.5, color: "EAF0F3", margin: 0, lineSpacingMultiple: 1.25,
    });
  });
  s.addNotes(NOTES[8]);
  footer(s);
}

// ---------------------------------------------------------------------------
// Slide 9 — Le variabili del modello
// ---------------------------------------------------------------------------
{
  const s = pres.addSlide();
  s.background = { color: WHITE };
  contentHeader(s, "04 · Il modello matematico", "Le variabili, ora per ora");

  const rows = [
    ["Potenze continue [MW]", "P_import, P_export, P_curtailment, P_charge, P_discharge, P_electrolyzer, P_fuel_cell", TEAL],
    ["Stati degli accumuli", "SoC (batteria) e SoH (idrogeno): frazione tra 0 e 1, con i limiti minimo e massimo del progetto", NAVY],
    ["Interruttori binari (0 o 1)", "delta_grid, delta_battery, delta_electrolyzer, delta_fuel_cell: impediscono scelte contraddittorie nella stessa ora", RED_SOFT],
  ];
  let y = 1.95;
  rows.forEach((r) => {
    const h = 1.22;
    card(s, MARGIN, y, W - 2 * MARGIN, h);
    s.addShape(pres.ShapeType.roundRect, {
      x: MARGIN, y, w: 0.14, h, rectRadius: 0,
      fill: { color: r[2] }, line: { type: "none" }, shadow: undefined,
    });
    s.addText(r[0], {
      x: MARGIN + 0.4, y: y + 0.16, w: 3.6, h: h - 0.32,
      fontFace: FONT_BODY, fontSize: 15, color: NAVY, bold: true, valign: "middle", margin: 0, lineSpacingMultiple: 1.1,
    });
    s.addText(r[1], {
      x: MARGIN + 4.2, y: y + 0.16, w: W - 2 * MARGIN - 4.5, h: h - 0.32,
      fontFace: "Courier New", fontSize: 12, color: INK, valign: "middle", margin: 0, lineSpacingMultiple: 1.2,
    });
    y += h + 0.18;
  });

  s.addText("Un interruttore binario, ad esempio, permette di comprare oppure vendere energia in un'ora, ma mai entrambe le cose insieme.", {
    x: MARGIN, y: y + 0.1, w: W - 2 * MARGIN, h: 0.5,
    fontFace: FONT_BODY, fontSize: 12.5, color: MUTED, italic: true, margin: 0,
  });
  s.addNotes(NOTES[9]);
  footer(s);
}

// ---------------------------------------------------------------------------
// Slide 10 — Il vincolo di bilancio di potenza
// ---------------------------------------------------------------------------
{
  const s = pres.addSlide();
  s.background = { color: WHITE };
  contentHeader(s, "04 · Il modello matematico", "Il vincolo più importante: il bilancio di potenza");

  s.addText("In ogni ora, tutta l'energia che entra nel sistema deve uguagliare esattamente tutta l'energia che esce.", {
    x: MARGIN, y: 2.0, w: W - 2 * MARGIN, h: 0.6,
    fontFace: FONT_BODY, fontSize: 15.5, color: INK, margin: 0,
  });

  const leftItems = ["Rinnovabile non sprecata", "+ Energia comprata dalla rete", "+ Energia dalla fuel cell", "+ Scarica della batteria"];
  const rightItems = ["Carico dell'edificio", "+ Energia venduta alla rete", "+ Energia all'elettrolizzatore", "+ Carica della batteria"];

  const boxW = 5.0, boxH = 3.3, y0 = 2.85;
  card(s, MARGIN, y0, boxW, boxH, { fill: "EAF6EE", line: "2F8F4E" });
  s.addText("ENTRA NEL SISTEMA", {
    x: MARGIN + 0.3, y: y0 + 0.25, w: boxW - 0.6, h: 0.35,
    fontFace: FONT_BODY, fontSize: 12.5, color: "2F8F4E", bold: true, charSpacing: 1, margin: 0,
  });
  leftItems.forEach((it, i) => {
    s.addText(it, {
      x: MARGIN + 0.3, y: y0 + 0.75 + i * 0.6, w: boxW - 0.6, h: 0.55,
      fontFace: FONT_BODY, fontSize: 13.5, color: INK, margin: 0, valign: "middle",
    });
  });

  circleLabel(s, W / 2, y0 + boxH / 2, 0.75, NAVY, "=", WHITE, 26);

  const rx = W - MARGIN - boxW;
  card(s, rx, y0, boxW, boxH, { fill: "FDEEEC", line: RED_SOFT });
  s.addText("ESCE DAL SISTEMA", {
    x: rx + 0.3, y: y0 + 0.25, w: boxW - 0.6, h: 0.35,
    fontFace: FONT_BODY, fontSize: 12.5, color: RED_SOFT, bold: true, charSpacing: 1, margin: 0,
  });
  rightItems.forEach((it, i) => {
    s.addText(it, {
      x: rx + 0.3, y: y0 + 0.75 + i * 0.6, w: boxW - 0.6, h: 0.55,
      fontFace: FONT_BODY, fontSize: 13.5, color: INK, margin: 0, valign: "middle",
    });
  });

  s.addText("Questa equazione vale per ogni singola ora della finestra di 24 ore, non solo per l'ora corrente.", {
    x: MARGIN, y: y0 + boxH + 0.25, w: W - 2 * MARGIN, h: 0.45,
    fontFace: FONT_BODY, fontSize: 12.5, color: MUTED, italic: true, align: "center", margin: 0,
  });
  s.addNotes(NOTES[10]);
  footer(s);
}

// ---------------------------------------------------------------------------
// Slide 11 — Batteria e idrogeno
// ---------------------------------------------------------------------------
{
  const s = pres.addSlide();
  s.background = { color: WHITE };
  contentHeader(s, "04 · Il modello matematico", "Batteria e idrogeno: la stessa logica");

  const cols = [
    {
      title: "BATTERIA", color: "8A5CBF",
      stats: [["1 MW", "potenza"], ["1 MWh", "capacità"], ["95%", "rendimento"]],
      desc: "Il livello di carica di ogni ora dipende da quello dell'ora prima. Caricare fa perdere un po' di energia; scaricare ne richiede un po' di più di quella che esce davvero: sono le normali perdite di ogni batteria reale.",
    },
    {
      title: "SISTEMA A IDROGENO", color: "C0433A",
      stats: [["20 MWh", "capacità"], ["10 MW", "elettr. / fuel cell"], ["73% / 65%", "rendimento"]],
      desc: "Stessa idea della batteria: produrre idrogeno (elettrolizzatore) lo riempie, consumarlo (fuel cell) lo svuota. I due non possono funzionare nella stessa ora.",
    },
  ];
  const colW = (W - 2 * MARGIN - 0.5) / 2;
  cols.forEach((c, i) => {
    const x = MARGIN + i * (colW + 0.5);
    const y = 2.05;
    const h = 4.55;
    card(s, x, y, colW, h);
    s.addShape(pres.ShapeType.roundRect, {
      x, y, w: colW, h: 0.14, fill: { color: c.color }, line: { type: "none" }, shadow: undefined,
    });
    s.addText(c.title, {
      x: x + 0.3, y: y + 0.35, w: colW - 0.6, h: 0.4,
      fontFace: FONT_BODY, fontSize: 15, color: c.color, bold: true, charSpacing: 1, margin: 0,
    });
    const statW = (colW - 0.6) / 3;
    c.stats.forEach((st, j) => {
      const sx = x + 0.3 + j * statW;
      s.addText(st[0], {
        x: sx, y: y + 0.85, w: statW - 0.1, h: 0.55,
        fontFace: FONT_TITLE, fontSize: 20, color: NAVY, bold: true, margin: 0,
      });
      s.addText(st[1], {
        x: sx, y: y + 1.38, w: statW - 0.1, h: 0.4,
        fontFace: FONT_BODY, fontSize: 10.5, color: MUTED, margin: 0,
      });
    });
    s.addText(c.desc, {
      x: x + 0.3, y: y + 2.0, w: colW - 0.6, h: h - 2.3,
      fontFace: FONT_BODY, fontSize: 13, color: INK, margin: 0, lineSpacingMultiple: 1.3,
    });
  });
  s.addNotes(NOTES[11]);
  footer(s);
}

// ---------------------------------------------------------------------------
// Slide 12 — La funzione obiettivo
// ---------------------------------------------------------------------------
{
  const s = pres.addSlide();
  s.background = { color: NAVY };
  s.addText("04 · IL MODELLO MATEMATICO", {
    x: MARGIN, y: 0.45, w: W - 2 * MARGIN, h: 0.35,
    fontFace: FONT_BODY, fontSize: 13, color: GOLD, bold: true, charSpacing: 2, margin: 0,
  });
  s.addText("La funzione obiettivo: cosa vogliamo minimizzare", {
    x: MARGIN, y: 0.78, w: W - 2 * MARGIN, h: 0.85,
    fontFace: FONT_TITLE, fontSize: 28, color: WHITE, bold: true, margin: 0,
  });

  card(s, MARGIN, 2.2, W - 2 * MARGIN, 1.7, { fill: NAVY_DARK, line: NAVY_DARK, shadow: false });
  s.addText([
    { text: "Costo totale  =  ", options: { color: "B9C9D4" } },
    { text: "spesa per comprare", options: { color: GOLD, bold: true } },
    { text: "  −  ", options: { color: "B9C9D4" } },
    { text: "ricavo dal vendere", options: { color: "6FCF97", bold: true } },
    { text: "  +  ", options: { color: "B9C9D4" } },
    { text: "penalità per lo spreco", options: { color: "F08A7C", bold: true } },
  ], {
    x: MARGIN + 0.4, y: 2.55, w: W - 2 * MARGIN - 0.8, h: 1.0,
    fontFace: FONT_TITLE, fontSize: 21, align: "center", valign: "middle", margin: 0,
  });

  s.addText(
    [
      { text: "La penalità per lo spreco (curtailment) non è un costo di mercato reale: è un numero scelto per orientare il modello.", options: { bullet: true, breakLine: true } },
      { text: "Nello script principale vale 1000 EUR/MWh, molto più dei prezzi normali (circa 500 EUR/MWh): il modello preferisce quasi sempre caricare la batteria, fare idrogeno o vendere in rete piuttosto che sprecare energia.", options: { bullet: true, breakLine: true } },
      { text: "In una variante di prova (es.py) questo valore è stato abbassato a 0.01 EUR/MWh, quasi zero, per vedere cosa succede se il freno economico allo spreco viene tolto.", options: { bullet: true, breakLine: false } },
    ],
    {
      x: MARGIN, y: 4.3, w: W - 2 * MARGIN, h: 2.5,
      fontFace: FONT_BODY, fontSize: 15, color: "E2EAEF", paraSpaceAfter: 12, lineSpacingMultiple: 1.25,
    }
  );
  s.addNotes(NOTES[12]);
  footer(s, "Project 16 — Controllo MPC di un sistema energetico industriale");
}

// ---------------------------------------------------------------------------
// Slide 13 — Il ciclo di simulazione
// ---------------------------------------------------------------------------
{
  const s = pres.addSlide();
  s.background = { color: WHITE };
  contentHeader(s, "04 · Il modello matematico", "Il ciclo di simulazione, ora per ora");

  const steps = [
    "Prepara i dati della finestra\n(previsione + valore vero dell'ora corrente)",
    "Risolve il modello MILP\nsulle prossime 24 ore",
    "Applica solo\nla 1ª decisione",
    "Aggiorna lo stato reale\n(batteria e idrogeno)",
    "Calcola il costo\ncon i dati veri",
  ];
  const n = steps.length;
  const boxW = 2.1, boxH = 1.5, gapArrow = 0.45;
  const totalW = n * boxW + (n - 1) * gapArrow;
  const startX = (W - totalW) / 2;
  const y = 2.6;
  steps.forEach((txt, i) => {
    const x = startX + i * (boxW + gapArrow);
    card(s, x, y, boxW, boxH, { fill: i % 2 === 0 ? TEAL : NAVY, line: i % 2 === 0 ? TEAL : NAVY, shadow: false });
    s.addText(String(i + 1), {
      x: x + 0.12, y: y + 0.08, w: 0.5, h: 0.4,
      fontFace: FONT_TITLE, fontSize: 16, color: GOLD, bold: true, margin: 0,
    });
    s.addText(txt, {
      x: x + 0.15, y: y + 0.45, w: boxW - 0.3, h: boxH - 0.55,
      fontFace: FONT_BODY, fontSize: 11.5, color: WHITE, align: "center", margin: 0, lineSpacingMultiple: 1.15,
    });
    if (i < n - 1) {
      s.addText("→", {
        x: x + boxW, y: y + boxH / 2 - 0.25, w: gapArrow, h: 0.5,
        fontFace: FONT_BODY, fontSize: 20, color: MUTED, align: "center", valign: "middle", margin: 0,
      });
    }
  });

  s.addShape(pres.ShapeType.line, {
    x: startX + boxW / 2, y: y + boxH + 0.35, w: totalW - boxW, h: 0.001,
    line: { color: GOLD, width: 2.25, beginArrowType: "triangle" },
  });
  s.addText("si ripete per ogni ora simulata", {
    x: startX, y: y + boxH + 0.55, w: totalW, h: 0.4,
    fontFace: FONT_BODY, fontSize: 12.5, color: NAVY, bold: true, align: "center", margin: 0,
  });

  s.addText("Nel codice questo ciclo è la funzione run_mpc_simulation, che chiama solve_mpc_step ad ogni ora.", {
    x: MARGIN, y: 6.15, w: W - 2 * MARGIN, h: 0.5,
    fontFace: FONT_BODY, fontSize: 12.5, color: MUTED, italic: true, align: "center", margin: 0,
  });
  s.addNotes(NOTES[13]);
  footer(s);
}

// ---------------------------------------------------------------------------
// Slide 14 — Struttura del codice
// ---------------------------------------------------------------------------
{
  const s = pres.addSlide();
  s.background = { color: WHITE };
  contentHeader(s, "05 · Il codice", "Come è organizzato lo script");

  card(s, MARGIN, 2.0, 3.0, 4.4, { fill: NAVY, line: NAVY, shadow: false });
  s.addText("main()", {
    x: MARGIN + 0.25, y: 2.25, w: 2.5, h: 0.45,
    fontFace: "Courier New", fontSize: 16, color: GOLD, bold: true, margin: 0,
  });
  s.addText("Mette in fila tutti i passi:\nargomenti → dati → solver →\nsimulazione → CSV e grafico", {
    x: MARGIN + 0.25, y: 2.75, w: 2.5, h: 3.4,
    fontFace: FONT_BODY, fontSize: 12.5, color: "E2EAEF", margin: 0, lineSpacingMultiple: 1.3,
  });

  const funcs = [
    ["load_project_data()", "legge i file .mat e prepara i dati"],
    ["select_solver()", "trova un solver Pyomo disponibile"],
    ["run_mpc_simulation()", "ripete il ciclo ora per ora"],
    ["solve_mpc_step()", "costruisce e risolve il modello MILP di una finestra"],
    ["save_results_csv() / create_plots()", "salvano la tabella oraria e il grafico riassuntivo"],
  ];
  let fy = 2.05;
  funcs.forEach((f) => {
    const fx = 4.3;
    const fw = W - MARGIN - fx;
    const fh = 0.78;
    card(s, fx, fy, fw, fh, { shadow: false });
    s.addText(f[0], {
      x: fx + 0.25, y: fy + 0.08, w: 4.0, h: fh - 0.16,
      fontFace: "Courier New", fontSize: 13, color: NAVY, bold: true, valign: "middle", margin: 0,
    });
    s.addText(f[1], {
      x: fx + 4.4, y: fy + 0.08, w: fw - 4.65, h: fh - 0.16,
      fontFace: FONT_BODY, fontSize: 12, color: MUTED, valign: "middle", margin: 0, lineSpacingMultiple: 1.1,
    });
    fy += fh + 0.13;
  });

  s.addText("es.py è una variante quasi identica: cambia solo il valore della penalità di curtailment (0.01 invece di 1000 EUR/MWh).", {
    x: MARGIN, y: 6.6, w: W - 2 * MARGIN, h: 0.4,
    fontFace: FONT_BODY, fontSize: 11.5, color: MUTED, italic: true, align: "center", margin: 0,
  });
  s.addNotes(NOTES[14]);
  footer(s);
}

// ---------------------------------------------------------------------------
// Slide 15 — Gli esperimenti condotti
// ---------------------------------------------------------------------------
{
  const s = pres.addSlide();
  s.background = { color: WHITE };
  contentHeader(s, "06 · Esperimenti e risultati", "Gli esperimenti condotti");

  s.addText("Per capire come si comporta il sistema, la simulazione sull'intero anno (6529 ore) è stata ripetuta in 4 scenari, ognuno risolto sia con Gurobi che con HiGHS:", {
    x: MARGIN, y: 2.0, w: W - 2 * MARGIN, h: 0.7,
    fontFace: FONT_BODY, fontSize: 14.5, color: INK, margin: 0, lineSpacingMultiple: 1.2,
  });

  const exps = [
    ["A", "Baseline", "SoC / SoH iniziali a metà (0.50 / 0.50)", TEAL],
    ["B", "Accumuli vuoti", "SoC / SoH iniziali al minimo (0.10 / 0.00)", NAVY],
    ["C", "Accumuli pieni", "SoC / SoH iniziali al massimo (0.90 / 1.00)", "8A5CBF"],
    ["D", "Penalità bassa", "Come C, ma penalità curtailment quasi nulla (0.01)", RED_SOFT],
  ];
  const cardW = (W - 2 * MARGIN - 3 * 0.35) / 4;
  exps.forEach((e, i) => {
    const x = MARGIN + i * (cardW + 0.35);
    const y = 2.95;
    const h = 3.1;
    card(s, x, y, cardW, h, { fill: e[3], line: e[3], shadow: false });
    circleLabel(s, x + cardW / 2, y + 0.65, 0.75, GOLD, e[0], NAVY_DARK, 22);
    s.addText(e[1], {
      x: x + 0.2, y: y + 1.25, w: cardW - 0.4, h: 0.5,
      fontFace: FONT_BODY, fontSize: 14.5, color: WHITE, bold: true, align: "center", margin: 0,
    });
    s.addText(e[2], {
      x: x + 0.2, y: y + 1.8, w: cardW - 0.4, h: 1.2,
      fontFace: FONT_BODY, fontSize: 11.5, color: "EAF0F3", align: "center", margin: 0, lineSpacingMultiple: 1.2,
    });
  });

  circleLabel(s, 1.5, 6.55, 0.34, TEAL, "G", WHITE, 12);
  s.addText("Gurobi (solver commerciale)", { x: 1.85, y: 6.35, w: 3.2, h: 0.4, fontFace: FONT_BODY, fontSize: 11.5, color: MUTED, valign: "middle", margin: 0 });
  circleLabel(s, 6.3, 6.55, 0.34, NAVY, "H", WHITE, 12);
  s.addText("HiGHS (solver open-source)", { x: 6.65, y: 6.35, w: 3.2, h: 0.4, fontFace: FONT_BODY, fontSize: 11.5, color: MUTED, valign: "middle", margin: 0 });
  s.addNotes(NOTES[15]);
  footer(s);
}

// ---------------------------------------------------------------------------
// Slide 16 — Risultati: il grafico
// ---------------------------------------------------------------------------
{
  const s = pres.addSlide();
  s.background = { color: WHITE };
  contentHeader(s, "06 · Esperimenti e risultati", "Un esperimento, visto ora per ora", { titleH: 0.7, titleSize: 26 });

  const imgPath = "../esperimenti_anno(gurobi)/expA_baseline/project16_plots.png";
  const imgW = 3.6;
  const imgH = imgW * (2560 / 2240);
  s.addImage({
    path: imgPath,
    x: MARGIN, y: 1.95, w: imgW, h: imgH,
    shadow: { type: "outer", color: "9AA7AF", opacity: 0.3, blur: 6, offset: 2, angle: 90 },
  });

  const notes = [
    ["Produzione e carico", "Rinnovabile vs. carico vs. curtailment: nel grafico il curtailment resta pressoché a zero per tutto l'anno."],
    ["Scambi controllati", "Import/export dalla rete, carica/scarica batteria, idrogeno: come si copre ogni ora il fabbisogno."],
    ["Livello degli accumuli", "SoC della batteria e SoH dell'idrogeno restano sempre entro i limiti imposti."],
    ["Costo cumulativo", "Il costo netto di mercato cresce in modo pressoché lineare nel corso dell'anno."],
  ];
  let ny = 1.95;
  const nx = MARGIN + imgW + 0.5;
  const nw = W - MARGIN - nx;
  notes.forEach((n, i) => {
    const nh = 1.05;
    card(s, nx, ny, nw, nh, { shadow: false });
    s.addShape(pres.ShapeType.roundRect, {
      x: nx, y: ny, w: 0.12, h: nh, fill: { color: [TEAL, NAVY, "8A5CBF", GOLD][i] }, line: { type: "none" }, shadow: undefined,
    });
    s.addText(n[0], {
      x: nx + 0.3, y: ny + 0.1, w: nw - 0.55, h: 0.32,
      fontFace: FONT_BODY, fontSize: 12.5, color: NAVY, bold: true, margin: 0,
    });
    s.addText(n[1], {
      x: nx + 0.3, y: ny + 0.42, w: nw - 0.55, h: nh - 0.5,
      fontFace: FONT_BODY, fontSize: 10.5, color: INK, margin: 0, lineSpacingMultiple: 1.12,
    });
    ny += nh + 0.15;
  });
  s.addText("Esperimento A (baseline), solver Gurobi — simulazione sull'intero anno (6529 ore)", {
    x: MARGIN, y: H - 1.05, w: imgW, h: 0.4,
    fontFace: FONT_BODY, fontSize: 10, color: MUTED, italic: true, margin: 0,
  });
  s.addNotes(NOTES[16]);
  footer(s);
}

// ---------------------------------------------------------------------------
// Slide 17 — Cosa fa davvero il sistema
// ---------------------------------------------------------------------------
{
  const s = pres.addSlide();
  s.background = { color: WHITE };
  contentHeader(s, "06 · Esperimenti e risultati", "Cosa fa davvero il sistema", { titleSize: 30 });

  const rows = [
    [TEAL, "Vive di rete", "L'importazione domina ogni ora: le rinnovabili da sole non bastano quasi mai a coprire il carico. Il costo cumulativo cresce sempre — l'impianto è un compratore netto di energia."],
    [NAVY, "Batteria = cuscinetto", "La carica sbatte di continuo tra 10% e 90%. Con 1 MWh contro flussi da più MW non può fare arbitraggio sui prezzi: serve solo a chiudere il bilancio orario."],
    ["8A5CBF", "Idrogeno spento", "Il serbatoio si svuota nei primi giorni e resta a 0 per tutto l'anno. Rese 73% / 65% e potenza minima 1 MW: con questi prezzi non conviene mai accenderlo."],
  ];
  let ry = 2.1;
  const rh = 1.35;
  rows.forEach(([c, title, body]) => {
    card(s, MARGIN, ry, W - 2 * MARGIN, rh, { shadow: false });
    s.addShape(pres.ShapeType.roundRect, {
      x: MARGIN, y: ry, w: 0.14, h: rh, fill: { color: c }, line: { type: "none" }, shadow: undefined,
    });
    s.addText(title, {
      x: MARGIN + 0.4, y: ry + 0.16, w: W - 2 * MARGIN - 0.8, h: 0.4,
      fontFace: FONT_BODY, fontSize: 16, color: NAVY, bold: true, margin: 0,
    });
    s.addText(body, {
      x: MARGIN + 0.4, y: ry + 0.58, w: W - 2 * MARGIN - 0.8, h: rh - 0.68,
      fontFace: FONT_BODY, fontSize: 12.5, color: INK, margin: 0, lineSpacingMultiple: 1.18,
    });
    ry += rh + 0.18;
  });
  s.addNotes(NOTES[17]);
  footer(s);
}

// ---------------------------------------------------------------------------
// Slide 18 — Gli accumuli, più da vicino
// ---------------------------------------------------------------------------
{
  const s = pres.addSlide();
  s.background = { color: WHITE };
  contentHeader(s, "06 · Esperimenti e risultati", "Gli accumuli, più da vicino", { titleSize: 30 });

  const imgW = 6.6;
  const imgH = imgW * (917 / 2319);
  s.addImage({
    path: "../grafici/03_livello_accumuli.png",
    x: MARGIN, y: 2.2, w: imgW, h: imgH,
    shadow: { type: "outer", color: "9AA7AF", opacity: 0.3, blur: 6, offset: 2, angle: 90 },
  });
  s.addText("Livello di batteria e idrogeno — zoom sulla prima settimana", {
    x: MARGIN, y: 2.2 + imgH + 0.12, w: imgW, h: 0.35,
    fontFace: FONT_BODY, fontSize: 10, color: MUTED, italic: true, margin: 0,
  });

  const nx = MARGIN + imgW + 0.5;
  const nw = W - MARGIN - nx;
  const items = [
    [NAVY, "Batteria sempre ai limiti", "La SoC resta tra 10% e 90% — vincolo rispettato — ma sbatte da un estremo all'altro: è sfruttata al massimo, e il massimo è poco."],
    [GOLD, "Idrogeno spento dopo pochi giorni", "La SoH parte dal 50%, si consuma subito e resta a zero. Ecco perché le condizioni iniziali quasi non cambiano i risultati."],
  ];
  let ny = 2.2;
  const nh = 2.15;
  items.forEach(([c, t, b]) => {
    card(s, nx, ny, nw, nh, { shadow: false });
    s.addShape(pres.ShapeType.roundRect, {
      x: nx, y: ny, w: 0.14, h: nh, fill: { color: c }, line: { type: "none" }, shadow: undefined,
    });
    s.addText(t, {
      x: nx + 0.35, y: ny + 0.2, w: nw - 0.6, h: 0.7,
      fontFace: FONT_BODY, fontSize: 13.5, color: NAVY, bold: true, margin: 0, lineSpacingMultiple: 1.1,
    });
    s.addText(b, {
      x: nx + 0.35, y: ny + 0.92, w: nw - 0.6, h: nh - 1.05,
      fontFace: FONT_BODY, fontSize: 11.5, color: INK, margin: 0, lineSpacingMultiple: 1.18,
    });
    ny += nh + 0.25;
  });
  s.addNotes(NOTES[18]);
  footer(s);
}

// ---------------------------------------------------------------------------
// Slide 19 — Risultati: confronto numerico (chart nativo)
// ---------------------------------------------------------------------------
{
  const s = pres.addSlide();
  s.background = { color: WHITE };
  contentHeader(s, "06 · Esperimenti e risultati", "Il costo cambia pochissimo tra scenari e solver");

  const categories = ["A · Baseline", "B · Vuoto", "C · Pieno", "D · Penalità bassa"];
  const gurobi = [9.67614, 9.67999, 9.67247, 9.67258];
  const highs = [9.67630, 9.68006, 9.67253, 9.67251];

  s.addChart(
    pres.ChartType.bar,
    [
      { name: "Gurobi", labels: categories, values: gurobi },
      { name: "HiGHS", labels: categories, values: highs },
    ],
    {
      x: MARGIN, y: 2.0, w: 8.6, h: 4.6,
      barDir: "col", barGrouping: "clustered",
      chartColors: [TEAL, GOLD],
      showTitle: true, title: "Costo netto di mercato per scenario (milioni di EUR, anno intero)",
      titleFontSize: 13, titleColor: NAVY,
      showValue: true, dataLabelPosition: "outEnd", dataLabelFontSize: 9, dataLabelColor: INK,
      dataLabelFormatCode: "0.000",
      catAxisLabelColor: INK, catAxisLabelFontSize: 11,
      valAxisLabelColor: MUTED, valAxisLabelFontSize: 10,
      valAxisTitle: "Milioni di EUR", showValAxisTitle: true, valAxisTitleFontSize: 11, valAxisTitleColor: MUTED,
      valAxisMinVal: 9.66, valAxisMaxVal: 9.69,
      valGridLine: { color: "E5EBEF", size: 1 },
      catGridLine: { style: "none" },
      showLegend: true, legendPos: "b", legendColor: INK, legendFontSize: 11,
    }
  );

  const statX = 9.9, statW = W - MARGIN - statX;
  card(s, statX, 2.0, statW, 4.6, { fill: NAVY, line: NAVY, shadow: false });
  s.addText("0 MWh", {
    x: statX + 0.25, y: 2.35, w: statW - 0.5, h: 0.8,
    fontFace: FONT_TITLE, fontSize: 34, color: GOLD, bold: true, align: "center", margin: 0,
  });
  s.addText("curtailment in TUTTI e 4 gli scenari, con entrambi i solver", {
    x: statX + 0.25, y: 3.2, w: statW - 0.5, h: 0.9,
    fontFace: FONT_BODY, fontSize: 12.5, color: WHITE, align: "center", margin: 0, lineSpacingMultiple: 1.2,
  });
  s.addShape(pres.ShapeType.line, {
    x: statX + 0.4, y: 4.25, w: statW - 0.8, h: 0.001,
    line: { color: "2E5975", width: 1 },
  });
  s.addText("< 0,01%", {
    x: statX + 0.25, y: 4.45, w: statW - 0.5, h: 0.6,
    fontFace: FONT_TITLE, fontSize: 22, color: WHITE, bold: true, align: "center", margin: 0,
  });
  s.addText("differenza di costo tra Gurobi e HiGHS", {
    x: statX + 0.25, y: 5.05, w: statW - 0.5, h: 0.7,
    fontFace: FONT_BODY, fontSize: 12, color: "CADCE8", align: "center", margin: 0, lineSpacingMultiple: 1.15,
  });
  s.addNotes(NOTES[19]);
  footer(s);
}

// ---------------------------------------------------------------------------
// Slide 20 — Scoperta interessante
// ---------------------------------------------------------------------------
{
  const s = pres.addSlide();
  s.background = { color: WHITE };
  contentHeader(s, "06 · Esperimenti e risultati", "Una scoperta inattesa", { titleSize: 30 });

  s.addText(
    [
      { text: "Nello scenario D la penalità sul curtailment è stata abbassata a quasi zero, aspettandosi più spreco di rinnovabile.", options: { bullet: true, breakLine: true } },
      { text: "Invece il curtailment resta a zero anche in questo scenario, sull'intero anno.", options: { bullet: true, breakLine: true } },
      { text: "Il motivo: su base annuale batteria, idrogeno ed export in rete offrono sempre abbastanza spazio per assorbire la produzione rinnovabile, anche quando gli accumuli partono già pieni.", options: { bullet: true, breakLine: true } },
      { text: "Il curtailment si osserva solo in un test sintetico dedicato (ultimo_test.py), costruito apposta con accumuli pieni e produzione rinnovabile molto più alta del carico.", options: { bullet: true, breakLine: false } },
    ],
    {
      x: MARGIN, y: 2.1, w: 7.4, h: 4.4,
      fontFace: FONT_BODY, fontSize: 15.5, color: INK, paraSpaceAfter: 14, lineSpacingMultiple: 1.28,
    }
  );

  const cx = 10.4, cyw = 2.5;
  card(s, cx - cyw / 2, 2.5, cyw, cyw + 1.0, { fill: GOLD, line: GOLD, shadow: false });
  s.addText("3 MW", {
    x: cx - cyw / 2, y: 2.85, w: cyw, h: 0.7,
    fontFace: FONT_TITLE, fontSize: 30, color: NAVY_DARK, bold: true, align: "center", margin: 0,
  });
  s.addText("curtailment atteso nel test sintetico:\nrinnovabile 15 − carico 2 − export max 10", {
    x: cx - cyw / 2 + 0.2, y: 3.65, w: cyw - 0.4, h: 1.6,
    fontFace: FONT_BODY, fontSize: 12, color: NAVY_DARK, align: "center", margin: 0, lineSpacingMultiple: 1.2,
  });
  s.addNotes(NOTES[20]);
  footer(s);
}

// ---------------------------------------------------------------------------
// Slide 21 — Conclusioni
// ---------------------------------------------------------------------------
{
  const s = pres.addSlide();
  s.background = { color: WHITE };
  contentHeader(s, "Conclusioni", "Cosa abbiamo imparato");

  const cols = [
    {
      title: "Cosa funziona", color: "2F8F4E",
      items: ["Il modello rispetta sempre bilancio di potenza e limiti di batteria/idrogeno", "I risultati sono praticamente identici tra Gurobi e HiGHS: non serve un solver a pagamento", "Il sistema riesce sempre a evitare lo spreco di rinnovabile, in ogni scenario annuale testato"],
    },
    {
      title: "Limiti e sviluppi futuri", color: RED_SOFT,
      items: ["La penalità di curtailment e gli stati iniziali sono scelte di modellazione, non dati nella consegna", "Il caso di spreco reale è stato osservato solo in un test sintetico, non nei dati veri di un anno", "Si potrebbe testare con condizioni meteo estreme, per vedere quando il curtailment diventa davvero necessario"],
    },
  ];
  const colW = (W - 2 * MARGIN - 0.5) / 2;
  cols.forEach((c, i) => {
    const x = MARGIN + i * (colW + 0.5);
    const y = 2.05;
    const h = 4.6;
    card(s, x, y, colW, h);
    s.addShape(pres.ShapeType.roundRect, {
      x, y, w: colW, h: 0.14, fill: { color: c.color }, line: { type: "none" }, shadow: undefined,
    });
    s.addText(c.title, {
      x: x + 0.3, y: y + 0.35, w: colW - 0.6, h: 0.45,
      fontFace: FONT_BODY, fontSize: 16, color: c.color, bold: true, margin: 0,
    });
    s.addText(
      c.items.map((it, j) => ({ text: it, options: { bullet: true, breakLine: j < c.items.length - 1 } })),
      {
        x: x + 0.3, y: y + 0.95, w: colW - 0.6, h: h - 1.25,
        fontFace: FONT_BODY, fontSize: 13.5, color: INK, paraSpaceAfter: 14, lineSpacingMultiple: 1.28,
      }
    );
  });
  s.addNotes(NOTES[21]);
  footer(s);
}

// ---------------------------------------------------------------------------
// Slide 22 — Grazie / Domande
// ---------------------------------------------------------------------------
{
  const s = pres.addSlide();
  s.background = { color: NAVY };
  s.addShape(pres.ShapeType.ellipse, {
    x: -1.8, y: H - 3.2, w: 5.0, h: 5.0,
    fill: { color: NAVY_DARK }, line: { type: "none" },
  });
  circleLabel(s, W - 1.4, 1.4, 0.9, GOLD, "P16", NAVY_DARK, 17);
  s.addText("Grazie per l'attenzione", {
    x: MARGIN, y: 3.0, w: W - 2 * MARGIN, h: 1.0,
    fontFace: FONT_TITLE, fontSize: 38, color: WHITE, bold: true, margin: 0,
  });
  s.addText("Domande?", {
    x: MARGIN, y: 3.85, w: W - 2 * MARGIN, h: 0.7,
    fontFace: FONT_BODY, fontSize: 20, color: GOLD, bold: true, margin: 0,
  });
  s.addText("Project 16 — Controllo MPC di un sistema energetico industriale\nCorso di Innovazione e Trasformazione Digitale — Prof. Francesco Conte (UCBM)", {
    x: MARGIN, y: 6.4, w: 10.5, h: 0.7,
    fontFace: FONT_BODY, fontSize: 12, color: TEAL_LIGHT, margin: 0, lineSpacingMultiple: 1.2,
  });
  s.addNotes(NOTES[22]);
}

pres.writeFile({ fileName: "Project16_Presentazione.pptx" }).then((fileName) => {
  console.log("Written:", fileName);
}).catch((err) => {
  console.error(err);
  process.exit(1);
});

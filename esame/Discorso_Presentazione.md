# Discorso per la presentazione — Project 16


---

### Slide 1 — Titolo

Buongiorno a tutti. Il progetto che presento oggi è il Project 16 del corso di Innovazione e Trasformazione Digitale, modulo del professor Francesco Conte. Ho realizzato un sistema di controllo che gestisce ora per ora un impianto energetico industriale dotato di pannelli solari, pale eoliche, una batteria, un sistema a idrogeno e un collegamento alla rete elettrica. L'obiettivo è decidere continuamente come usare queste risorse per minimizzare i costi, rispettando tutti i vincoli tecnici dell'impianto.

### Slide 2 — Indice

La presentazione è organizzata in sei parti. Partirò dal problema che dovevo risolvere, poi descriverò il sistema fisico dell'impianto. Spiegherò cos'è il controllo MPC, il tipo di controllo che ho usato per prendere le decisioni ora per ora. Dopodiché entrerò nel modello matematico che sta dietro ogni decisione, mostrerò come ho strutturato il codice, e concluderò con gli esperimenti che ho condotto e i risultati ottenuti, con numeri reali.

### Slide 3 — Il problema

Il problema di partenza è questo: abbiamo un impianto che produce energia da fonti rinnovabili, ha una batteria e un sistema a idrogeno per accumulare energia, ed è collegato alla rete elettrica per comprare o vendere energia quando serve. Ogni ora bisogna decidere come gestire tutte queste risorse insieme, rispettando quattro obiettivi principali dati dalla consegna del progetto: minimizzare il costo netto di mercato, soddisfare sempre il carico dell'edificio, che non è controllabile, mantenere la batteria sempre tra il 10 e il 90 per cento di carica, e minimizzare lo spreco di energia rinnovabile, quello che in gergo si chiama curtailment.

### Slide 4 — Il sistema fisico

Questo è lo schema dell'impianto. Al centro c'è un bus energetico, un punto virtuale dove tutta l'energia si incontra e deve bilanciarsi. Da un lato abbiamo le fonti rinnovabili, 4 megawatt di fotovoltaico e 8 di eolico. Dall'altro lato la rete elettrica, con cui possiamo importare fino a 12 megawatt o esportare fino a 10. In basso ci sono gli accumuli: una batteria da 1 megawatt e 1 megawattora, e un sistema a idrogeno da 20 megawattora, con un elettrolizzatore per produrlo e una fuel cell per riconvertirlo in energia. In alto c'è il carico dell'edificio, che dobbiamo sempre soddisfare e che non possiamo controllare.

### Slide 5 — Da dove vengono i dati

Tutti questi dati arrivano da tre file forniti con il progetto. Il primo contiene la produzione rinnovabile prevista e reale per ogni ora dell'anno. Il secondo contiene i consumi dell'edificio. Il terzo è il PUN, il prezzo unico nazionale, cioè il prezzo di mercato a cui possiamo vendere l'energia in eccesso. Il prezzo di acquisto invece non arriva da nessun file: segue una regola fissa con tre fasce orarie, che ho implementato direttamente nel codice.

### Slide 6 — Cos'è il controllo MPC

Il tipo di controllo che ho usato si chiama Model Predictive Control, o MPC. L'idea è questa: ogni ora, il sistema guarda le prossime 24 ore e calcola il piano ottimo per quel periodo, usando le previsioni disponibili in quel momento. È un po' come pianificare la settimana: siamo abbastanza sicuri di cosa succederà domani, ma il meteo di venerdì è solo una stima, e potrebbe cambiare.

### Slide 7 — Perché si applica solo la prima ora

Una domanda che mi sono posto subito è: se calcoliamo un piano di 24 ore, perché non lo applichiamo tutto? La risposta è che le previsioni per le ore future possono sbagliare. Quindi applichiamo solo la prima decisione del piano, quella basata sul dato vero e non su una previsione. Poi aggiorniamo lo stato reale della batteria e dell'idrogeno, e ricalcoliamo tutto da capo per l'ora successiva, con dati più aggiornati. In questo modo il sistema si corregge continuamente, invece di seguire alla cieca un piano vecchio.

### Slide 8 — Il modello MILP

Per calcolare il piano di ogni finestra di 24 ore, ho costruito un modello matematico di ottimizzazione con la libreria Pyomo, risolto poi con un solver, in questo caso Gurobi oppure HiGHS. Questo tipo di modello si chiama MILP, un problema lineare misto intero, e si compone di tre parti: le variabili, cioè cosa il modello può decidere; i vincoli, cioè le regole che non può violare; e la funzione obiettivo, cioè cosa deve minimizzare.

### Slide 9 — Le variabili

Le variabili del modello si dividono in tre gruppi. Ci sono le potenze continue, come quanta energia importare, esportare, o quanta caricare e scaricare la batteria. Ci sono gli stati degli accumuli, cioè il livello di carica della batteria e quello dell'idrogeno. E infine ci sono delle variabili binarie, che funzionano come interruttori: valgono solo 0 o 1, e servono a impedire scelte contraddittorie, come comprare e vendere energia nella stessa ora.

### Slide 10 — Il bilancio di potenza

Il vincolo più importante del modello è il bilancio di potenza. In ogni singola ora, tutta l'energia che entra nel sistema, la rinnovabile non sprecata, quella comprata dalla rete, quella dalla fuel cell, la scarica della batteria, deve uguagliare esattamente tutta l'energia che esce: il carico dell'edificio, l'energia venduta, quella usata per produrre idrogeno, e quella per caricare la batteria. Questo vincolo vale per ognuna delle 24 ore della finestra, non solo per l'ora corrente.

### Slide 11 — Batteria e idrogeno

Batteria e sistema a idrogeno seguono la stessa logica. Il livello di ogni ora dipende da quello dell'ora precedente: se carico, il livello sale; se scarico, scende. In entrambi i casi ho tenuto conto dei rendimenti reali: la batteria ha un rendimento del 95 per cento sia in carica che in scarica, mentre l'idrogeno ha un rendimento del 73 per cento per l'elettrolizzatore e del 65 per cento per la fuel cell. E naturalmente elettrolizzatore e fuel cell non possono funzionare nella stessa ora.

### Slide 12 — La funzione obiettivo

La funzione obiettivo è quella che il modello cerca di minimizzare: il costo netto di mercato, cioè quanto spendiamo per comprare energia meno quanto guadagniamo vendendola, più una penalità per ogni megawatt di rinnovabile sprecato. Questa penalità non è un costo reale di mercato, ma un numero che ho scelto io per orientare il comportamento del modello. Nello script principale l'ho impostata a 1000 euro per megawattora, un valore molto più alto dei prezzi normali, proprio per rendere lo spreco l'ultima opzione possibile. Ho anche creato una variante con questa penalità abbassata quasi a zero, per vedere cosa sarebbe cambiato: ne parlo più avanti nei risultati.

### Slide 13 — Il ciclo di simulazione

Ecco come funziona in pratica il ciclo di simulazione, ora per ora. Prima si preparano i dati della finestra, con la previsione e il valore vero dell'ora corrente. Poi si risolve il modello MILP sulle 24 ore. Si applica solo la prima decisione. Si aggiorna lo stato reale di batteria e idrogeno. E infine si calcola il costo usando i dati veri, non le previsioni. Questo ciclo si ripete per ogni ora che vogliamo simulare, che sia una settimana o un anno intero.

### Slide 14 — Struttura del codice

Dal punto di vista del codice, tutto parte dalla funzione main, che mette in fila i vari passi: legge gli argomenti da riga di comando, carica i dati con load_project_data, sceglie un solver disponibile con select_solver, esegue la simulazione ora per ora con run_mpc_simulation, che a sua volta chiama solve_mpc_step per ogni singola ora, e infine salva i risultati in un file CSV e crea un grafico riassuntivo. Ho anche creato una seconda versione dello script, es.py, identica in tutto tranne che per il valore della penalità sul curtailment.

### Slide 15 — Gli esperimenti condotti

Per capire davvero come si comporta il sistema, non mi sono fermato a una singola simulazione. Ho ripetuto la simulazione sull'intero anno, quindi più di 6500 ore, in quattro scenari diversi: uno di base con gli accumuli a metà carica, uno con gli accumuli completamente vuoti, uno con gli accumuli completamente pieni, e uno identico al terzo ma con la penalità sul curtailment abbassata quasi a zero. Ho ripetuto ognuno di questi quattro scenari sia con il solver Gurobi che con il solver open source HiGHS, per un totale di otto simulazioni complete sull'anno.

### Slide 16 — Risultati: il grafico

Questo è il risultato di uno di questi esperimenti, lo scenario di base risolto con Gurobi. Il grafico ha quattro pannelli: in alto la produzione rinnovabile confrontata con il carico e con il curtailment, che resta praticamente sempre a zero; poi gli scambi controllati con rete, batteria e idrogeno; poi il livello degli accumuli, che si mantiene sempre dentro i limiti imposti; e infine il costo cumulativo di mercato, che cresce in modo quasi lineare durante l'anno.

### Slide 17 — Cosa fa davvero il sistema

I grafici, oltre a dirci che i vincoli sono rispettati, raccontano come si comporta il sistema, e ci sono tre cose che vale la pena far notare. La prima: l'impianto compra quasi sempre energia dalla rete. Nel pannello degli scambi domina l'importazione, perché la produzione rinnovabile da sola non basta quasi mai a coprire il carico, e infatti il costo cumulativo cresce sempre: l'impianto è nel complesso un compratore netto di energia. La seconda: la batteria lavora quasi sempre attaccata a uno dei due limiti, il 10 o il 90 per cento, e salta di continuo da un estremo all'altro. È troppo piccola, un solo megawattora contro flussi da diversi megawatt, per spostare davvero energia da un'ora costosa a una economica: di fatto serve solo da cuscinetto per chiudere il bilancio orario. La terza, la più curiosa: il sistema a idrogeno si svuota nei primi giorni e poi resta fermo a zero per tutto il resto dell'anno. Con rendimenti del 73 e del 65 per cento e una potenza minima di un megawatt, in questo scenario di prezzi non conviene mai metterlo in funzione.

### Slide 18 — Gli accumuli, più da vicino

Questo è lo zoom sulla prima settimana del livello dei due accumuli. La linea della batteria, in blu, rimbalza di continuo tra il 10 e il 90 per cento: non esce mai dalla fascia ammessa, quindi il vincolo è sempre rispettato, ma si vede che viene usata al massimo delle sue possibilità, che però sono poche. La linea dell'idrogeno, in arancione, parte dal 50 per cento, viene consumata nei primi giorni e poi resta incollata a zero. Questo spiega anche perché le condizioni iniziali contano così poco: qualunque sia il punto di partenza, dopo poche ore la batteria è tornata ai suoi limiti e l'idrogeno si è svuotato, e il sistema di fatto dimentica da dove è partito.

### Slide 19 — Confronto numerico

Mettendo a confronto tutti gli otto risultati emergono due cose interessanti. Primo: il costo cambia pochissimo tra i quattro scenari, meno dello 0,1 per cento, segno che le condizioni iniziali di batteria e idrogeno contano poco su un anno intero, come si vedeva anche dal grafico degli accumuli. Secondo: la differenza tra Gurobi e HiGHS è minima, meno dello 0,01 per cento: per questo modello il solver gratuito HiGHS è più che sufficiente, senza bisogno di una licenza commerciale.

### Slide 20 — Una scoperta inattesa

C'è un risultato che non mi aspettavo. Nello scenario D avevo abbassato la penalità sul curtailment quasi a zero, aspettandomi che il sistema sprecasse più energia rinnovabile. Invece il curtailment è rimasto a zero anche in questo caso, per tutto l'anno. Il motivo è soprattutto l'export verso la rete: visto che l'idrogeno resta fermo e la batteria è minuscola, è la vendita in rete a fare da valvola di sfogo per gli eccessi di rinnovabile, e con il limite di 10 megawatt in esportazione lo spazio è sempre sufficiente, anche quando gli accumuli partono già pieni. Ho osservato un vero caso di curtailment solo in un test sintetico che ho costruito apposta, con accumuli pieni e una produzione rinnovabile molto più alta del carico: in quel caso il modello ha sprecato esattamente i 3 megawatt che avevo calcolato a mano, confermando che il modello si comporta correttamente.

### Slide 21 — Conclusioni

Per concludere: il modello rispetta sempre il bilancio di potenza e tutti i vincoli tecnici di batteria e idrogeno. I risultati sono praticamente identici tra il solver commerciale e quello open source, quindi non è necessario un solver a pagamento per questo tipo di problema. E il sistema riesce sempre a evitare lo spreco di rinnovabile in tutti gli scenari annuali testati, appoggiandosi soprattutto alla rete: l'impianto è di fatto un compratore netto di energia, la batteria fa solo da cuscinetto e il sistema a idrogeno, con questi prezzi, resta quasi sempre fermo. Ci sono anche dei limiti: la penalità sul curtailment e gli stati iniziali sono scelte di modellazione mie, non specificate dalla consegna, e il caso di spreco reale l'ho osservato solo in un test sintetico. Uno sviluppo futuro interessante potrebbe essere testare condizioni meteo estreme, per capire quando il curtailment diventa davvero necessario anche su dati reali.



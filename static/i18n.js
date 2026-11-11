/* StencilIt — internationalisation (English by default, French).
 *
 * The application code writes its texts in French; this layer translates them on display:
 *  - EN: exact French -> English matches (texts, tooltips, options…);
 *  - PATTERNS: dynamic texts (with numbers, names…) recognised by regular expression;
 *  - an observer translates everything that appears in the page (server messages included) and
 *    remembers the original, to switch back to French instantly.
 * Elements marked data-noi18n (user-entered names, language selector) are ignored.
 */
(function () {
  "use strict";
  const LS = "stencilit.lang";

  // ------------------------------------------------------------------ exact
  const EN = {
    // Header, tabs, bars
    "pochoirs multicouches pour l'aérographe": "multi-layer airbrush stencils",
    "Chargez une image pour commencer": "Load an image to get started",
    "Derniers réglages restaurés — chargez une image": "Last settings restored — load an image",
    "Réglages par défaut": "Default settings",
    "Rétablit tous les réglages par défaut ; l'image chargée et ses masques sont conservés, ainsi que les réglages enregistrés": "Restores all default settings; the loaded image and its masks are kept, as well as the saved presets",
    "Réglages par défaut rétablis (image conservée)": "Default settings restored (image kept)",
    "Calcul auto": "Auto compute",
    "Préférences": "Preferences", "Préférences (langue, chargement des images)": "Preferences (language, image loading)",
    "Au chargement d'une image, l'ajuster au mieux dans le pochoir": "When an image is loaded, fit it best in the stencil",
    "Même effet que le bouton « Ajuster au mieux dans le pochoir » (section « Image : cadrage & taille »). Ne s'applique pas à l'ouverture d'un projet.": "Same effect as the “Best fit in the stencil” button (“Image: crop & size” section). Not applied when opening a project.",
    "Au chargement d'une image, la taille et la position sont choisies pour que l'image soit la plus grande possible dans le pochoir (support, feuille ou tapis selon la mise en page).": "When an image is loaded, its size and position are chosen so that it is as large as possible in the stencil (support, sheet or mat depending on the layout).",
    "Coché : chaque modification relance le calcul. Décoché : le calcul ne se fait qu'à la demande (bouton à côté, ou Ctrl + Entrée).": "Checked: every change recomputes. Unchecked: compute only on demand (button next to it, or Ctrl + Enter).",
    "À jour ✓": "Up to date ✓",
    "Recalculer ●": "Recompute ●",
    "Calcul en cours…": "Computing…",
    "Des réglages ont changé depuis le dernier calcul : cliquer pour recalculer (Ctrl + Entrée)": "Settings changed since the last computation: click to recompute (Ctrl + Enter)",
    "Le résultat correspond aux réglages actuels (cliquer pour recalculer quand même)": "The result matches the current settings (click to recompute anyway)",
    "Calcul automatique": "Automatic computation",
    "Calcul à la demande : bouton « Recalculer » ou Ctrl + Entrée": "On-demand computation: “Recompute” button or Ctrl + Enter",
    "Cadrage": "Crop", "Mise en page": "Layout", "Masques": "Masks", "Prévisualisation": "Preview",
    "Comparer à l'original": "Compare with original", "Original": "Original",
    "Masques peints au pinceau : zones des détails clés (pochoir de contours) ou sujet à garder (fond supprimé)": "Brush-painted masks: key-detail areas (outline stencil) or subject to keep (background removed)",
    "Support": "Support", "Tapis": "Mat", "Couches": "Layers", "Tout afficher": "Show all",
    "Rendu simulé": "Simulated render", "(flou de l'aérographe)": "(airbrush blur)", "Prétraitée": "Preprocessed",
    "Support : sa couleur sous la prévisualisation, son bord et la feuille du pochoir en pointillés verts, dans toutes les vues et à la même échelle. Désactivé : les couches seules, sur fond transparent.": "Support: its colour under the preview, its edge and the stencil sheet (green dashes), in every view at the same scale. Off: layers only, on a transparent background.",
    "Tapis de découpe (feuille posée dans son coin) dans toutes les vues, à la même échelle": "Cutting mat (sheet placed in its corner) in every view, at the same scale",
    "Onglet Original : image prétraitée (activé) ou image d'origine brute": "Original tab: preprocessed image (on) or raw original image",
    "Masque contours (détails clés)": "Outline mask (key details)", "Masque sujet (fond supprimé)": "Subject mask (background removed)",
    "Masque à peindre": "Mask to paint", "Outil": "Tool", "Pinceau": "Brush", "Gomme": "Eraser",
    "Peindre une zone (B)": "Paint an area (B)", "Effacer (E)": "Erase (E)", "Taille": "Size", "Taille du pinceau": "Brush size",
    "Afficher le masque": "Show mask", "Tout effacer": "Clear all", "px": "px",
    "Aucune image chargée.": "No image loaded.",
    "Glissez une image ici": "Drop an image here", "ou cliquez pour choisir": "or click to choose",
    "Ouvrir un projet…": "Open a project…",
    "Rouvrir un zip exporté par StencilIt (image, masque et tous les réglages), ou seulement son fichier …_infos.json": "Reopen a zip exported by StencilIt (image, masks and all settings), or just its …_infos.json file",
    "Exporter les SVG + projet (.zip)": "Export SVGs + project (.zip)",
    "Pochoirs SVG + projet rechargeable (image d'origine, masque, réglages)": "SVG stencils + reloadable project (original image, mask, settings)",
    "Glisser pour élargir / réduire (double-clic : largeur par défaut)": "Drag to widen / narrow (double-click: default width)",
    "Largeur du panneau des réglages": "Settings panel width", "Largeur de la colonne des pochoirs": "Stencil column width",
    // Stencil column
    "Pochoirs": "Stencils", "matière": "material", "ouverture": "opening", "pont": "bridge", "détail supprimé": "removed detail",
    "Afficher / masquer les ponts sur les vues des couches": "Show / hide bridges on the layer views",
    "Afficher / masquer les détails supprimés par les contraintes du matériau": "Show / hide details removed by the material constraints",
    "Les pochoirs apparaîtront ici, dans l'ordre de pulvérisation.": "Stencils will appear here, in spraying order.",
    "Palette de couleurs…": "Colour palette…", "Palettes de couleurs": "Colour palettes",
    "Colore les couches avec une palette cohérente : chaque couche reçoit la couleur de la palette la plus proche de sa teinte dans l'image (jamais deux fois la même) ; chaque couleur reste modifiable ensuite": "Colours the layers with a consistent palette: each layer gets the palette colour closest to its tone in the image (never the same one twice); each colour stays editable afterwards",
    "Revenir aux teintes calculées pour toutes les couches": "Back to the computed tones for all layers",
    "Plus proches": "Closest",
    "Donne à chaque couche la couleur de la palette la plus proche de sa teinte réelle dans l'image (deux couches n'ont jamais la même couleur) ; sans palette choisie, prend la palette qui colle le mieux à l'image": "Gives each layer the palette colour closest to its real tone in the image (two layers never get the same colour); with no palette chosen, picks the palette that best matches the image",
    "＋ Enregistrer les couleurs actuelles…": "＋ Save the current colours…",
    "Enregistre les couleurs actuelles des couches (de la 1re à la dernière) comme palette réutilisable": "Saves the current layer colours (first to last) as a reusable palette",
    "Nom de la palette": "Palette name", "Mes palettes": "My palettes",
    "Classiques": "Classics", "Vives": "Vivid", "Douces": "Soft", "Nature": "Nature", "Monochromes": "Monochromes",
    "Vives modernes": "Modern vivid", "Douces modernes": "Modern soft",
    "Froides": "Cold", "Chaudes": "Warm",
    "Pluie violette": "Purple rain",
    "Dégradé bleu-vert": "Blue-green gradient",
    "Côte bleue": "Blue coast",
    "Abysse marine": "Navy abyss",
    "Nuit violette": "Violet night",
    "Lavande pastel": "Pastel lavender",
    "Lagon": "Lagoon",
    "Vert frais": "Fresh green",
    "Eaux calmes": "Calm waters",
    "Ciel bleu": "Blue sky",
    "Bleu profond": "Deep blue",
    "Eaux silencieuses": "Silent waters",
    "Mousse": "Moss",
    "Retraite cosy": "Cosy retreat",
    "Récolte d'automne": "Autumn harvest",
    "Sorbet pêche": "Peach sorbet",
    "Terres chaudes": "Warm earths",
    "Cerisier en fleur": "Cherry blossom",
    "Dégradé soleil": "Sun gradient",
    "Ombré rose": "Pink ombre",
    "Lueur d'automne": "Autumn glow",
    "Rustique": "Rustic",
    "Tons terreux": "Earthy tones",
    "Couchant d'automne": "Autumn sunset",
    "Lueur dorée": "Golden glow",
    "Tendances": "Trending", "Jardin d'olivier": "Olive garden", "Océan ardent": "Fiery ocean", "Grands fonds": "Deep sea",
    "Rêve pastel": "Pastel dream", "Moisson": "Harvest", "Brise d'été": "Summer breeze", "Braise": "Embers",
    "Coucher sur l'océan": "Ocean sunset", "Noir & or": "Black & gold", "Rose bonbon": "Candy pink", "Sable doux": "Soft sand",
    "Plage ensoleillée": "Sunny beach", "Été doré": "Golden summer", "Harmonie neutre": "Neutral harmony", "Acier clair": "Light steel",
    "Lavande fumée": "Smoky lavender", "Crépuscule doré": "Golden twilight", "Pétales de rose": "Rose petals", "Bord de mer": "Seaside",
    "Électro": "Electro", "Acidulé": "Candy", "Miami": "Miami", "Corail & turquoise": "Coral & turquoise",
    "Graffiti urbain": "Urban graffiti", "Memphis": "Memphis", "Agrumes": "Citrus", "Cyberpunk": "Cyberpunk",
    "Scandinave": "Scandinavian", "Sorbet": "Sorbet", "Sauge & argile": "Sage & clay", "Terracotta douce": "Soft terracotta",
    "Brume": "Mist", "Pêche & menthe": "Peach & mint", "Rose poudré": "Powder pink", "Aube": "Dawn",
    "Naturel (terres)": "Natural (earths)", "Sépia": "Sepia", "Niveaux de gris": "Greyscale", "Sombre": "Dark", "Vintage": "Vintage",
    "Cuivre": "Copper", "Vifs": "Vivid", "Pop art": "Pop art", "Sérigraphie pop": "Pop screen print", "Bande dessinée": "Comic book",
    "Street art": "Street art", "Néon": "Neon", "Tropical": "Tropical", "Rétro années 70": "70s retro", "Pastel": "Pastel",
    "Printemps": "Spring", "Lavande": "Lavender", "Nordique": "Nordic", "Océan": "Ocean", "Forêt": "Forest", "Automne": "Autumn",
    "Désert": "Desert", "Glace": "Ice", "Coucher de soleil": "Sunset", "Camouflage": "Camouflage", "Bleu de Prusse": "Prussian blue",
    "Sanguine": "Red chalk", "Indigo (japonais)": "Indigo (Japanese)", "Rouge et noir": "Red and black", "Olive": "Olive",
    "masquée": "hidden", "visible": "visible", "auto": "auto",
    "Afficher / masquer dans la prévisualisation": "Show / hide in the preview",
    "Couleur de la couche": "Layer colour", "Couleurs des couches": "Layer colours",
    "Teintes de l'image (calculées)": "Image tones (computed)", "Dernières couleurs utilisées": "Recently used colours",
    "Aucune pour l'instant": "None yet", "Couleur personnalisée": "Custom colour",
    "Saturation (horizontal) et luminosité (vertical)": "Saturation (horizontal) and brightness (vertical)",
    "Teinte": "Hue", "Code couleur hexadécimal": "Hexadecimal colour code", "Appliquer": "Apply",
    "Auto (teinte calculée)": "Auto (computed tone)", "Revenir à la teinte calculée": "Back to the computed tone",
    "Calage à la règle — depuis le coin haut-gauche du support": "Ruler positioning — from the support's top-left corner",
    "Tracez au crayon une croix à chaque cote, puis posez chaque couche en alignant ses fenêtres en croix sur les traits.": "Pencil a cross at each dimension, then lay each layer by aligning its cross windows on the marks.",
    "Croix": "Cross", "depuis la gauche": "from left", "depuis le haut": "from top", "depuis la droite": "from right", "depuis le bas": "from bottom",
    "Recommandé :": "Recommended:", "Écart à l'original (ΔE) selon le nombre de pochoirs :": "Difference from original (ΔE) by number of stencils:",
    "Support :": "Support:", "Feuille du pochoir :": "Stencil sheet:", "Image :": "Image:",
    "Écart à l'original (ΔE moyen) :": "Difference from original (mean ΔE):", "(plus bas = plus fidèle)": "(lower = more faithful)",
    "Ponts :": "Bridges:", "Longueur de coupe totale :": "Total cut length:",
    "Bord du support": "Support edge", "Feuille du pochoir": "Stencil sheet",
    "Image prétraitée sur le support": "Preprocessed image on the support", "Image d'origine sur le support": "Original image on the support",
    "Image source — peignez le sujet à garder": "Source image — paint the subject to keep",
    "Image source — peignez les zones à détailler": "Source image — paint the areas to detail",
    "Partie de l'image utilisée (recadrage)": "Part of the image used (crop)", "Position de la comparaison": "Comparison position",
    "Histogramme de luminance et seuils entre les teintes": "Luminance histogram and thresholds between tones",
    "Chargez une image pour voir l'histogramme": "Load an image to see the histogram",
    // Surface to paint
    "Support à peindre": "Surface to paint", "Format": "Format", "Portrait": "Portrait", "Paysage": "Landscape",
    "Format du support (grand côté / petit côté selon l'orientation)": "Support format (long side / short side according to orientation)",
    "Papier ISO": "ISO paper", "Toiles & cadres du commerce (cm)": "Standard canvases & frames (cm)",
    "Châssis français — Figure (F)": "French stretchers — Figure (F)", "Châssis français — Paysage (P)": "French stretchers — Landscape (P)",
    "Châssis français — Marine (M)": "French stretchers — Marine (M)", "Découpe": "Cutting",
    "27,5 × 27,5 cm (tapis 12″ avec 15 mm de marge)": "27.5 × 27.5 cm (12″ mat with 15 mm margin)",
    "Personnalisé": "Custom", "Largeur du support (mm)": "Support width (mm)", "Hauteur du support (mm)": "Support height (mm)",
    "Couleur du support": "Support colour", "Support enregistré": "Saved support", "— Choisir un support enregistré —": "— Choose a saved support —",
    "(aucun support enregistré)": "(no saved support)", "Nom du support": "Support name", "Nom (ex. Toile 30×40 kraft)": "Name (e.g. Kraft canvas 30×40)",
    "Format, couleur, marge intérieure, feuille du pochoir et repères de calage.": "Format, colour, inner margin, stencil sheet and registration marks.",
    "Enregistrer": "Save", "Enregistrer sous…": "Save as…", "Renommer…": "Rename…", "Supprimer": "Delete", "OK": "OK", "Annuler": "Cancel",
    "● modifié": "● modified", "Les valeurs ont été modifiées depuis le dernier enregistrement": "Values changed since the last save",
    "Enregistrer les valeurs actuelles dans le support sélectionné": "Save the current values into the selected support",
    "Enregistrer sous un nouveau nom": "Save under a new name", "Renommer le support sélectionné": "Rename the selected support",
    "Supprimer le support sélectionné": "Delete the selected support",
    "Enregistrer les valeurs actuelles dans le matériau ★ sélectionné": "Save the current values into the selected ★ material",
    "Renommer le matériau ★ sélectionné": "Rename the selected ★ material", "Supprimer le matériau ★ sélectionné": "Delete the selected ★ material",
    "Nom du matériau": "Material name", "Nom (ex. Mylar 0,125 Cameo 4)": "Name (e.g. Mylar 0.125 Cameo 4)",
    // Image: crop & size
    "Image : cadrage & taille": "Image: crop & size", "Recadrage": "Crop", "Libre": "Free", "Proportions du support": "Support proportions",
    "Carré 1:1": "Square 1:1", "Tout": "All", "(onglet « Cadrage » pour tracer le cadre)": "(“Crop” tab to draw the frame)",
    "Taille (% de « ajusté »)": "Size (% of “fit”)", "Largeur de l'image (mm)": "Image width (mm)", "Hauteur de l'image (mm)": "Image height (mm)",
    "Conserver les proportions": "Keep proportions", "Aligner sur le support": "Align on support", "Distance au bord (mm)": "Distance from edge (mm)",
    "Coin haut-gauche": "Top-left corner", "Centré en haut": "Top centre", "Coin haut-droit": "Top-right corner",
    "Centré à gauche": "Middle left", "Centré": "Centre", "Centré à droite": "Middle right",
    "Coin bas-gauche": "Bottom-left corner", "Centré en bas": "Bottom centre", "Coin bas-droit": "Bottom-right corner",
    "Centrer horizontalement": "Centre horizontally", "Centrer verticalement": "Centre vertically",
    "Position horizontale (%)": "Horizontal position (%)", "Position verticale (%)": "Vertical position (%)",
    "Ajuster": "Fit", "Remplir": "Fill", "Centrer": "Centre", "Ajuster au mieux dans le pochoir": "Best fit in the stencil",
    "Image entière dans le support, marge intérieure comprise": "Whole image within the support, inner margin included",
    "L'image couvre tout le support (bords rognés)": "The image covers the whole support (edges cropped)",
    "Agrandit ou réduit l'image au maximum que permet le pochoir : support (feuille autour du support) ou tapis de découpe (feuille ajustée au motif), bordure comprise. Choisit au besoin l'orientation du tapis qui donne la plus grande image.": "Scales the image to the largest size the stencil allows: support (sheet around the support) or cutting mat (sheet fitted to the design), border included. Picks the mat orientation giving the largest image if needed.",
    "Marge intérieure pour « Ajuster » (mm)": "Inner margin for “Fit” (mm)",
    "Faites glisser l'image dans l'onglet « Mise en page » ; poignée en bas à droite = taille.": "Drag the image in the “Layout” tab; bottom-right handle = size.",
    // Preprocessing
    "Prétraitement de l'image": "Image preprocessing", "Niveaux automatiques": "Auto levels",
    "(étire les tons du plus sombre au plus clair)": "(stretches tones from darkest to lightest)",
    "Contraste local": "Local contrast", "Tons moyens (gamma)": "Midtones (gamma)",
    "Contraste local : fait ressortir les volumes (visage, plis) avant le découpage en teintes. Gamma > 1 éclaircit les tons moyens, < 1 les assombrit.": "Local contrast: brings out volumes (face, folds) before splitting into tones. Gamma > 1 lightens midtones, < 1 darkens them.",
    "Saturation (%)": "Saturation (%)", "Netteté": "Sharpness",
    "Saturation : sépare mieux les teintes proches d'une image couleur. Netteté : surtout utile au pochoir de contours (détails clés) ; au-delà d'un réglage léger, elle crée du bruit.": "Saturation: better separates close tones of a colour image. Sharpness: mostly useful for the outline stencil (key details); beyond a light setting it adds noise.",
    "Supprimer le fond (il reste support nu)": "Remove the background (left as bare support)", "Peindre le sujet…": "Paint the subject…",
    "Aucun sujet peint.": "No subject painted.", "Seuils manuels entre les teintes": "Manual thresholds between tones",
    "Seuils automatiques": "Automatic thresholds", "Revenir aux seuils calculés automatiquement": "Back to the automatically computed thresholds",
    "Réinitialiser": "Reset", "Aucun prétraitement": "No preprocessing",
    "Faites glisser un trait de l'histogramme pour déplacer la frontière entre deux teintes (les seuils manuels s'activent alors). Sous l'histogramme : la teinte de chaque plage, puis la couleur de la couche qui la peint (son numéro ; S = laissée au support).": "Drag a line on the histogram to move the boundary between two tones (manual thresholds then turn on). Under the histogram: each range's tone, then the colour of the layer painting it (its number; S = left to the support).",
    "Le nombre de teintes a changé : seuils repartis depuis le calcul automatique. Ajustez-les sur l'histogramme.": "The number of tones changed: thresholds restarted from the automatic computation. Adjust them on the histogram.",
    // Sheet & registration
    "Feuille du pochoir & calage": "Stencil sheet & registration",
    "Autour du support (support + marge)": "Around the support (support + margin)",
    "Dans le support, ajustée au motif (+ bordure)": "Inside the support, fitted to the design (+ border)",
    "Marge autour du support (mm)": "Margin around the support (mm)",
    "Feuille de matière": "Material sheet", "Orientation de la feuille de matière": "Material sheet orientation",
    "Non précisée (pas de contrôle)": "Not specified (no check)", "Machine": "Machine", "Feuille": "Sheet", "Rouleau": "Roll",
    "Contour de la feuille du pochoir (pointillés verts) et feuille de matière (posée dans le même coin) dans toutes les vues, à la même échelle": "Stencil sheet outline (green dashes) and material sheet (laid in the same corner) in every view, at the same scale",
    "Indiquez le format de la feuille de matière pour vérifier que le pochoir peut y être découpé en entier.": "Give the material sheet format to check that the stencil can be cut from it in full.",
    "Choisissez le format de la feuille de matière (section Machine de découpe)": "Choose the material sheet format (Cutting machine section)",
    "Format de la feuille de matière dans laquelle le pochoir est découpé : sert uniquement à vérifier que le pochoir y tient en entier (il ne change pas le pochoir).": "Format of the material sheet the stencil is cut from: only used to check that the stencil fits on it in full (it does not change the stencil).",
    "Portrait ou paysage : intervertit la largeur et la hauteur de la feuille de matière.": "Portrait or landscape: swaps the material sheet width and height.",
    "Largeur de la feuille de matière, en mm.": "Material sheet width, in mm.", "Hauteur de la feuille de matière, en mm.": "Material sheet height, in mm.",
    "Papier US": "US paper", "Feuilles pour machine de découpe": "Cutting-machine sheets", "Mes formats": "My formats",
    "Letter — 8,5 × 11″ (215,9 × 279,4 mm)": "Letter — 8.5 × 11″ (215.9 × 279.4 mm)",
    "Legal — 8,5 × 14″ (215,9 × 355,6 mm)": "Legal — 8.5 × 14″ (215.9 × 355.6 mm)",
    "Tabloid — 11 × 17″ (279,4 × 431,8 mm)": "Tabloid — 11 × 17″ (279.4 × 431.8 mm)",
    "12 × 12″ (304,8 × 304,8 mm)": "12 × 12″ (304.8 × 304.8 mm)", "12 × 24″ (304,8 × 609,6 mm)": "12 × 24″ (304.8 × 609.6 mm)",
    "24 × 24″ (609,6 × 609,6 mm)": "24 × 24″ (609.6 × 609.6 mm)",
    "Zoom": "Zoom", "Zoom avant": "Zoom in", "Zoom arrière": "Zoom out",
    "Zoom avant (molette vers le haut)": "Zoom in (mouse wheel up)", "Zoom arrière (molette vers le bas)": "Zoom out (mouse wheel down)",
    "Ajuster à la vue (double-clic sur l'image). Zoomé : glisser (Cadrage, Mise en page, Masques : bouton du milieu ou Espace + glisser) pour se déplacer": "Fit to view (double-click on the image). Zoomed in: drag to move around (Crop, Layout, Masks: middle button or Space + drag)",
    "Repères": "Marks", "Cotes": "Dimensions", "Masquer": "Hide",
    "Panneau des cotes de calage à la règle, sous la prévisualisation": "Panel of the ruler registration dimensions, below the preview",
    "Masquer le panneau des cotes (bouton « Cotes » au-dessus de la vue pour le réafficher)": "Hide the dimensions panel (“Dimensions” button above the view to show it again)",
    "Repères de calage (croix, équerres ou trous) et encoches du numéro de couche, dans toutes les vues": "Registration marks (crosses, L-brackets or holes) and layer-number notches, in every view",
    "Mes formats de feuille": "My sheet formats", "tient sur la feuille ✓": "fits on the sheet ✓", "dépasse de la feuille ✗": "overflows the sheet ✗",
    "Enregistrer la taille actuelle dans le format ★ sélectionné": "Save the current size into the selected ★ format",
    "Renommer le format ★ sélectionné": "Rename the selected ★ format", "Supprimer le format ★ sélectionné": "Delete the selected ★ format",
    "Nom du format de feuille": "Sheet format name", "Nom (ex. Rhodoïd 50 × 65)": "Name (e.g. Acetate 50 × 65)",
    "Bordure autour du motif (mm)": "Border around the design (mm)", "= tapis": "= mat", "Prendre la taille du tapis de découpe": "Use the cutting mat size",
    "Cotes à la règle pour tracer les croix sur le support": "Ruler dimensions to draw the crosses on the support",
    "Feuille posée sur le support : tracez au crayon les croix aux cotes indiquées, puis alignez chaque couche dessus.": "Sheet laid on the support: pencil the crosses at the given dimensions, then align each layer on them.",
    "Le pochoir déborde du support ; calage sur les angles du support (équerres) ou croix dans la marge.": "The stencil overhangs the support; register on the support corners (L-brackets) or crosses in the margin.",
    "Machine de découpe": "Cutting machine", "Silhouette Cameo 4 (largeur de coupe 305 mm)": "Silhouette Cameo 4 (305 mm cutting width)",
    "Silhouette Cameo 5 (largeur de coupe 305 mm)": "Silhouette Cameo 5 (305 mm cutting width)",
    "Silhouette Cameo Pro (largeur de coupe 610 mm)": "Silhouette Cameo Pro (610 mm cutting width)", "Autre machine": "Other machine",
    "Largeur de coupe (mm)": "Cutting width (mm)", "Tapis de découpe": "Cutting mat",
    "Tapis standard 12 × 12″ (304,8 × 304,8 mm)": "Standard mat 12 × 12″ (304.8 × 304.8 mm)", "Tapis long 12 × 24″ (304,8 × 609,6 mm)": "Long mat 12 × 24″ (304.8 × 609.6 mm)",
    "Tapis Cameo Pro 24 × 24″ (609,6 × 609,6 mm)": "Cameo Pro mat 24 × 24″ (609.6 × 609.6 mm)", "Sans tapis (matière en rouleau)": "No mat (roll material)",
    "Orientation du tapis par rapport au support (paysage = tapis tourné d'un quart de tour ; tournez le dessin de même dans Silhouette Studio)": "Mat orientation relative to the support (landscape = mat turned a quarter turn; rotate the design likewise in Silhouette Studio)",
    "Repères d'alignement": "Registration marks", "3 coins (détrompeur)": "3 corners (keyed)", "4 coins": "4 corners", "Aucun": "None",
    "Équerres sur les angles du support": "L-brackets on the support corners", "Croix de repérage": "Registration crosses", "Trous pour pions": "Peg holes",
    "Taille des repères (mm)": "Mark size (mm)", "Encoches = numéro de couche": "Notches = layer number", "Découper le contour de la feuille": "Cut the sheet outline",
    "Fentes en L à l'extérieur des angles du support : le pochoir est en place quand chaque angle du support affleure le coin intérieur du L.": "L-shaped slots outside the support corners: the stencil is in place when each support corner meets the inner corner of the L.",
    "À la 1re couche, reportez les croix au crayon (ou sur un adhésif) ; alignez ensuite chaque couche sur ces croix.": "On the 1st layer, transfer the crosses in pencil (or onto tape); then align each layer on these crosses.",
    "Trous pour pions ou punaises de calage (diamètre = taille). Fixez les pions sur la planche à travers la 1re couche.": "Holes for registration pegs or pins (diameter = size). Fix the pegs on the board through the 1st layer.",
    "Le coin bas-droit sans repère sert de détrompeur.": "The bottom-right corner without a mark acts as a key.",
    // Simplification
    "Simplification": "Simplification", "Nombre de pochoirs": "Number of stencils", "Niveau de détail": "Level of detail", "Poids de la teinte (%)": "Hue weight (%)", "Vivacité des couleurs (%)": "Colour vividness (%)", "Mode": "Mode",
    "Automatique": "Automatic", "Couleur": "Colour", "Noir & blanc / niveaux de gris": "Black & white / greyscale",
    "Superposition des couches": "Layer stacking", "Cumulative (du clair au foncé, chevauchement)": "Cumulative (light to dark, overlapping)",
    "Exclusive (chaque couleur seule)": "Exclusive (each colour alone)",
    "Cumulatif : chaque pochoir ouvre sa couleur + les plus foncées. Moins de pièces fragiles et pas de liseré entre couleurs.": "Cumulative: each stencil opens its colour + the darker ones. Fewer fragile pieces and no gap between colours.",
    "La teinte la plus proche du support reste nue (pas de pochoir)": "The tone closest to the support stays bare (no stencil)",
    // Outlines
    "Contours des détails clés": "Key-detail outlines", "Retracer les détails clés estompés": "Redraw the faded key details",
    "Où mettre les traits": "Where the lines go", "Pochoir de contours séparé (peint en dernier)": "Separate outline stencil (painted last)",
    "Dans la couche la plus foncée": "In the darkest layer", "Dans la couche de teinte la plus proche": "In the layer of the nearest tone",
    "Un pochoir de plus, peint en dernier, de la couleur du trait choisie ci-dessous.": "One more stencil, painted last, in the line colour chosen below.",
    "Pas de pochoir en plus : les traits sont découpés dans la dernière couche (la plus foncée). Elle aura plus d'îlots et de ponts.": "No extra stencil: the lines are cut into the last (darkest) layer. It will have more islands and bridges.",
    "Pas de pochoir en plus : chaque trait va dans la couche de teinte la plus proche de la sienne, parmi celles plus foncées que la zone qu'il traverse.": "No extra stencil: each line goes into the layer whose tone is closest to its own, among those darker than the area it crosses.",
    "Pochoir séparé : un pochoir de plus, peint en dernier, de la couleur choisie. Dans une couche : pas de pochoir en plus, les traits sont découpés dans une couche de couleur (plus foncée que la zone qu'ils traversent).": "Separate stencil: one more stencil, painted last, in the chosen colour. In a layer: no extra stencil, the lines are cut into a colour layer (darker than the area they cross).",
    "Protéger les traits fins de la simplification (yeux, sourcils, mèches…)": "Protect thin strokes from simplification (eyes, eyebrows, strands…)",
    "Les traits fins, sombres ou clairs (yeux, sourcils, narines, mèches), gardent leur teinte au lieu d'être absorbés par la zone voisine lors de la simplification. Les traits plus fins que l'ouverture mini disparaissent quand même : utilisez alors « Retracer les détails clés estompés ».": "Thin dark or light strokes (eyes, eyebrows, nostrils, strands) keep their tone instead of being absorbed by the area around them during simplification. Strokes thinner than the minimum opening still disappear: then use “Redraw the faded key details”.",
    "Détecte automatiquement les détails nets de l'image que la simplification et le flou de l'aérographe estompent (yeux, traits fins, mèches…) et les redessine d'un trait fin.": "Automatically detects the sharp details that simplification and airbrush blur fade (eyes, fine lines, strands…) and redraws them with a thin line.",
    "Pour limiter la recherche à certaines zones (visage, yeux…), peignez-les dans l'onglet": "To limit the search to some areas (face, eyes…), paint them in the tab",
    "« Masque contours »": "“Outline mask”", "Sensibilité": "Sensitivity",
    "Bas : seulement les détails les plus marqués · haut : beaucoup de détails.": "Low: only the strongest details · high: many details.",
    "Largeur du trait (mm)": "Line width (mm)", "Longueur mini d'un trait (mm)": "Minimum line length (mm)",
    "Le trait n'est jamais plus fin que l'ouverture mini du matériau.": "The line is never thinner than the material's minimum opening.",
    "Couleur du trait": "Line colour", "Automatique (teinte la plus contrastée avec le support)": "Automatic (tone with most contrast against the support)",
    "Méthode de détection": "Detection method", "Bords nets (Canny)": "Sharp edges (Canny)",
    "Trait dessiné (DoG)": "Drawn line (DoG)", "Lignes fines (crêtes)": "Thin lines (ridges)",
    "Voir la détection…": "Show detection…",
    "Bords nets de l'image (luminance et couleur). Polyvalent, mais un trait fin donne deux bords parallèles.": "Sharp edges of the image (luminance and colour). Versatile, but a thin line gives two parallel edges.",
    "Un seul trait le long de chaque contour, du côté sombre, comme un dessin à la plume. Peu sensible au bruit.": "A single line along each contour, on its dark side, like a pen drawing. Not very sensitive to noise.",
    "Ligne centrale des traits fins (cils, sourcils, rides, mèches) : un seul trait là où Canny en trouve deux.": "Centre line of thin strokes (lashes, eyebrows, wrinkles, strands): a single line where Canny finds two.",
    "Comment les détails sont trouvés : bords nets (Canny), trait dessiné le long des contours (DoG) ou ligne centrale des traits fins (crêtes).": "How details are found: sharp edges (Canny), a line drawn along the contours (DoG) or the centre line of thin strokes (ridges).",
    "Ouvre l'onglet Masques avec l'aperçu de la détection : traits retenus, trop courts et non retenus, en direct.": "Opens the Masks tab with the detection preview: kept, too short and discarded lines, live.",
    "Superpose les traits détectés pour le pochoir de contours (calculés avec les couches du dernier calcul et les réglages de contours actuels).": "Overlays the lines detected for the outline stencil (computed with the layers of the last computation and the current outline settings).",
    "Aperçu de la détection": "Detection preview", "trait du pochoir": "stencil line", "trop court": "too short",
    "détecté, non retenu": "detected, not kept",
    "Fusion au lieu des ponts": "Merge instead of bridges", "Largeur max d'un chenal (mm)": "Max channel width (mm)",
    "Fermer les chenaux étroits": "Close narrow channels", "Supprimer les petits îlots": "Remove small islands",
    "… y compris ceux entourés par les traits des détails clés": "… including those enclosed by key-detail lines",
    "Quand les traits des détails clés sont mis dans une couche, ils encerclent souvent de petites zones claires qui demandent chacune un pont. Coché : ces petits îlots peuvent aussi être supprimés (peints), dans la même limite de surface ; le trait lui-même n'est jamais coupé. Attention : l'intérieur d'un petit motif cerclé (un œil…) peut alors être rempli.": "When key-detail lines are put in a layer, they often enclose small light areas that each need a bridge. Checked: these small islands may be removed (painted) too, within the same area limit; the line itself is never cut. Beware: the inside of a small circled motif (an eye…) may then be filled.",
    "Désactivée : les îlots sont toujours tenus par des ponts.": "Off: islands are always held by bridges.",
    "fusion": "merge",
    "Afficher / masquer les zones fusionnées au lieu d'un pont (chenal fermé ou petit îlot supprimé)": "Show / hide the zones merged instead of a bridge (closed channel or removed small island)",
    "Au lieu d'un pont, ferme un chenal étroit (l'îlot se soude au reste de la feuille) ou supprime un petit îlot (il est peint), si la zone modifiée reste petite. 0 = toujours des ponts. Une zone repeinte ensuite par une couche plus foncée ne compte pas ; la modification compte moins si les deux teintes sont proches.": "Instead of a bridge, closes a narrow channel (the island is welded to the rest of the sheet) or removes a small island (it gets painted), if the changed area stays small. 0 = always bridges. An area repainted later by a darker layer does not count; the change counts less when both tones are close.",
    "Seuls les passages d'ouverture plus étroits que cette largeur peuvent être fermés (au-delà, c'est une vraie zone peinte).": "Only opening passages narrower than this width may be closed (wider ones are real painted areas).",
    "Ferme les chenaux d'ouverture étroits qui séparent un îlot du reste de la matière (la peinture de ce chenal est perdue).": "Closes the narrow opening channels that separate an island from the rest of the material (the paint of that channel is lost).",
    "Supprime les petits îlots de matière : ils sont peints avec la couche (le petit détail clair est perdu).": "Removes small material islands: they are painted with the layer (the small light detail is lost).", "déjà dans la couche": "already in the layer", "Lancez d'abord un calcul.": "Run a computation first.",
    "Aperçu de la détection : lancez d'abord un calcul": "Detection preview: run a computation first",
    "Erreur de l'aperçu de la détection": "Detection preview error",
    // Material
    "Matériau & découpe": "Material & cutting", "Matériau & réglages de découpe": "Material & cutting settings", "Mes matériaux": "My materials",
    "Mon matériau": "My material", "Ouverture mini (mm)": "Minimum opening (mm)", "Bande de matière mini (mm)": "Minimum material strip (mm)",
    "Surface mini d'une pièce (mm²)": "Minimum piece area (mm²)", "Ponts automatiques (îlots)": "Automatic bridges (islands)",
    "Largeur des ponts (mm)": "Bridge width (mm)", "Ponts minimum par îlot": "Minimum bridges per island", "2 ponts au-delà de (mm²)": "2 bridges above (mm²)",
    "Les ponts d'un même îlot sont répartis tout autour. Plus de ponts = îlots mieux tenus (papier, grands îlots), mais plus de traces à retoucher.": "An island's bridges are spread all around it. More bridges = better-held islands (paper, large islands), but more marks to touch up.",
    "Réglages de la machine": "Machine settings", "Lame": "Blade", "Force": "Force", "Vitesse": "Speed", "Passes": "Passes", "Notes": "Notes",
    "Ces valeurs sont reprises en commentaire dans les SVG exportés.": "These values are written as comments in the exported SVGs.",
    "Faites toujours un test de coupe.": "Always do a test cut.",
    "Vos matériaux apparaissent avec ★ dans la liste en haut de la section. Les matériaux fournis ne sont pas modifiables : « Enregistrer » crée alors une copie.": "Your materials appear with ★ in the list at the top of the section. Built-in materials cannot be changed: “Save” then creates a copy.",
    "Papier épais / carte (160-300 g/m²)": "Heavy paper / card (160-300 gsm)", "Vinyle adhésif": "Adhesive vinyl", "Mylar (0,1-0,19 mm)": "Mylar (0.1-0.19 mm)",
    "Le papier se déchire facilement : préférez des ponts larges et des bandes de matière généreuses.": "Paper tears easily: prefer wide bridges and generous material strips.",
    // Vectorisation
    "Vectorisation & aperçu": "Vectorisation & preview", "Tolérance des tracés (mm)": "Path tolerance (mm)", "Courbes lisses (Bézier)": "Smooth curves (Bézier)",
    "Flou de pulvérisation (mm)": "Spray blur (mm)", "Résolution de calcul (px/mm)": "Computation resolution (px/mm)",
    "Plus haut = plus précis mais plus lent.": "Higher = more precise but slower.",
    // Messages
    "Chargement…": "Loading…", "Ouverture du projet…": "Opening project…", "Détourage du sujet…": "Cutting out the subject…",
    "Sujet détouré": "Subject cut out", "Masque sujet effacé": "Subject mask cleared", "Fond supprimé (sujet peint)": "Background removed (subject painted)",
    "Pochoir de contours activé (masque peint)": "Outline stencil enabled (mask painted)", "Pochoir de contours activé": "Outline stencil enabled", "Couleurs calculées pour toutes les couches": "Computed colours for all layers",
    "Calculez d'abord les couches": "Compute the layers first", "Chargez d'abord une image": "Load an image first",
    "Choisissez d'abord un tapis de découpe": "Choose a cutting mat first", "Donnez un nom à la palette": "Give the palette a name",
    "Image chargée — réglages du projet appliqués": "Image loaded — project settings applied",
    "Réglages du projet appliqués à l'image chargée": "Project settings applied to the loaded image",
    "Réglages du projet chargés — chargez maintenant l'image d'origine": "Project settings loaded — now load the original image",
    "Ce JSON n'est pas un fichier …_infos.json de StencilIt": "This JSON is not a StencilIt …_infos.json file", "Fichier JSON illisible": "Unreadable JSON file",
    "Projet illisible": "Unreadable project", "Erreur du masque": "Mask error", "Erreur du masque sujet": "Subject mask error", "Erreur": "Error",
    "Masque illisible": "Unreadable mask", "Session inconnue, rechargez l'image": "Unknown session, reload the image", "Aucune image reçue": "No image received",
    "Aucun fichier reçu": "No file received", "Ce fichier n'est pas un zip de projet StencilIt": "This file is not a StencilIt project zip",
    "Fichier …_infos.json introuvable dans le zip": "…_infos.json file not found in the zip", "Rien à exporter": "Nothing to export",
    "Nom ou valeurs manquants": "Missing name or values", "Type de réglage inconnu": "Unknown preset type", "Nouveau nom manquant": "New name missing",
    "Image illisible": "Unreadable image",
    "Peignez le sujet dans l'onglet « Masques » (masque Sujet) pour supprimer le fond": "Paint the subject in the “Masks” tab (Subject mask) to remove the background",
    "Aucune zone peinte : les détails clés sont cherchés sur toute l'image.": "No painted area: key details are searched over the whole image.",
    "Peignez grossièrement le sujet (en débordant un peu) : le fond autour est détecté et supprimé.": "Roughly paint the subject (overlapping a little): the surrounding background is detected and removed.",
    "Cliquez sur le sujet avec l'outil Objet, ou peignez-le grossièrement (en débordant un peu) : le fond autour est détecté et supprimé.": "Click the subject with the Object tool, or roughly paint it (overlapping a little): the surrounding background is detected and removed.",
    "Objet": "Object",
    "Sélection d'objet (S) : cliquez sur un objet pour l'ajouter au masque, recliquez dessus pour changer de découpage (partie, objet, ensemble), Alt + clic pour retirer un objet. Le pinceau et la gomme restent utilisables pour retoucher.": "Object selection (S): click an object to add it to the mask, click it again for another cut (part, object, whole), Alt + click to remove an object. The brush and eraser can still be used to touch up.",
    "Analyse de l'image pour la sélection d'objet…": "Analysing the image for object selection…",
    "Sélection d'objet indisponible": "Object selection unavailable",
    "Sélection d'objet prête : cliquez sur un objet (Alt + clic pour le retirer)": "Object selection ready: click an object (Alt + click to remove it)",
    "Erreur de la sélection d'objet": "Object selection error",
    "Requête de sélection invalide": "Invalid selection request",
    "Modèle de sélection téléchargé corrompu (empreinte SHA-256 inattendue)": "Downloaded selection model is corrupt (unexpected SHA-256 hash)",
    "Module onnxruntime absent : relancez lancer.bat (qui installe les dépendances de requirements.txt)": "onnxruntime module missing: restart lancer.bat (it installs the dependencies of requirements.txt)",
    "Support foncé : les zones sombres laissées au support deviennent des îlots dans les couches claires, et leurs ponts resteront visibles. Pour des aplats foncés sans pont, décochez « La teinte la plus proche du support reste nue ».": "Dark support: dark areas left to the support become islands in the light layers, and their bridges will stay visible. For dark flat areas without bridges, uncheck “The tone closest to the support stays bare”.",
    "L'image dépasse du support : elle est rognée à ses bords (impression à fond perdu).": "The image overflows the support: it is cropped at its edges (full bleed).",
    "L'image est entièrement hors du support : elle a été recentrée.": "The image is entirely outside the support: it has been re-centred.",
    // Recommendation
    "la courbe ne se stabilise pas : image riche en nuances": "the curve does not level off: image rich in shades",
    "une teinte de plus n'améliore presque plus le rendu": "one more tone hardly improves the render",
    "une teinte de plus ne couvrirait qu'une surface négligeable": "one more tone would only cover a negligible area",
    // Summaries
    "aucun": "none", "désactivé": "disabled", "niveaux": "levels", "seuils manuels": "manual thresholds", "fond supprimé": "background removed",
    "toute l'image": "whole image", "masque": "mask", "croix": "crosses", "équerres": "l-brackets", "trous": "holes",
    "tient sur le tapis ✓": "fits on the mat ✓",
    "contours": "outline", "couleur": "colour", "noir & blanc": "black & white", "dépasse du tapis ✗": "exceeds the mat ✗", "passe ✓": "fits ✓",
    "passe tournée d'un quart de tour": "fits turned a quarter turn", "trop large ✗": "too wide ✗",
    "haut-gauche": "top-left", "haut-droite": "top-right", "bas-gauche": "bottom-left", "bas-droite": "bottom-right",
  };

  // ------------------------------------------------------------------ setting tooltips (TIPS)
  Object.assign(EN, {
    "Image à transformer en pochoirs (photo, dessin, logo… en couleur ou noir et blanc). Vous pouvez aussi la glisser sur la zone.": "Image to turn into stencils (photo, drawing, logo… in colour or black and white). You can also drop it on the area.",
    "Projet StencilIt exporté (.zip) ou son fichier …_infos.json.": "Exported StencilIt project (.zip) or its …_infos.json file.",
    "Vos supports enregistrés : format, couleur, marges, feuille, tapis et repères de calage.": "Your saved supports: format, colour, margins, sheet, mat and registration marks.",
    "Portrait ou paysage : intervertit la largeur et la hauteur du support.": "Portrait or landscape: swaps the support width and height.",
    "Largeur réelle de la surface à peindre, en millimètres.": "Real width of the surface to paint, in millimetres.",
    "Hauteur réelle de la surface à peindre, en millimètres.": "Real height of the surface to paint, in millimetres.",
    "Couleur de la surface avant peinture. Elle sert de fond à l'aperçu ; la teinte de l'image la plus proche peut rester « nue » (sans pochoir).": "Colour of the surface before painting. It is the preview background; the closest image tone can stay “bare” (no stencil).",
    "Proportions imposées au cadre de recadrage (onglet Cadrage) : libres, celles du support, ou un rapport fixe.": "Proportions imposed on the crop frame (Crop tab): free, the support's, or a fixed ratio.",
    "Revient à l'image entière, sans recadrage.": "Back to the whole image, no crop.",
    "Taille de l'image en % de la taille « ajustée au support » (100 % = l'image tient dans le support, marge intérieure comprise).": "Image size as % of the “fit to support” size (100 % = the image fits the support, inner margin included).",
    "Largeur de l'image sur le support, en mm (la hauteur suit si « Garder les proportions » est coché).": "Image width on the support, in mm (height follows if “Keep proportions” is checked).",
    "Hauteur de l'image sur le support, en mm.": "Image height on the support, in mm.",
    "Coché : largeur et hauteur restent proportionnelles. Décoché : l'image peut être étirée.": "Checked: width and height stay proportional. Unchecked: the image can be stretched.",
    "Distance au bord du support utilisée par les boutons d'alignement (coins, milieux des bords).": "Distance from the support edge used by the alignment buttons (corners, edge middles).",
    "Position horizontale du centre de l'image, en % de la largeur du support (50 % = centrée).": "Horizontal position of the image centre, as % of the support width (50 % = centred).",
    "Position verticale du centre de l'image, en % de la hauteur du support (50 % = centrée).": "Vertical position of the image centre, as % of the support height (50 % = centred).",
    "Centre l'image sur le support sans changer sa taille.": "Centres the image on the support without changing its size.",
    "Marge gardée libre tout autour de l'image par « Ajuster » (et la taille 100 %).": "Margin kept free around the image by “Fit” (and the 100 % size).",
    "Étire les tons de l'image du plus sombre au plus clair avant le découpage en teintes (utile pour les photos ternes).": "Stretches the image tones from darkest to lightest before splitting into tones (useful for dull photos).",
    "Contraste local : accentue les volumes (visage, plis) zone par zone. 0 = désactivé.": "Local contrast: enhances volumes (face, folds) area by area. 0 = off.",
    "Tons moyens : au-dessus de 1 éclaircit, en dessous assombrit, sans toucher au noir et au blanc.": "Midtones: above 1 lightens, below darkens, without touching black and white.",
    "Saturation des couleurs (100 % = inchangée) : plus haut sépare mieux les teintes proches d'une image couleur.": "Colour saturation (100 % = unchanged): higher better separates close tones of a colour image.",
    "Netteté (masque flou, ≈ 0,3 mm) : surtout utile au pochoir de contours ; trop forte, elle crée du bruit.": "Sharpness (unsharp mask, ≈ 0.3 mm): mostly useful for the outline stencil; too strong, it adds noise.",
    "Le fond détouré (masque Sujet) reste support nu : aucun pochoir n'y est découpé.": "The cut-out background (Subject mask) stays bare support: no stencil is cut there.",
    "Ouvre l'onglet Masques sur le masque Sujet : peignez grossièrement le sujet à garder.": "Opens the Masks tab on the Subject mask: roughly paint the subject to keep.",
    "Chaque teinte devient une plage de luminance que vous réglez en glissant les traits de l'histogramme.": "Each tone becomes a luminance range that you set by dragging the histogram lines.",
    "Feuille autour du support (calage sur ses angles) ou posée dans le support (ajustée au motif, calage par croix et cotes).": "Sheet around the support (registered on its corners) or laid inside the support (fitted to the design, registered with crosses and dimensions).",
    "Marge de la feuille autour du support : elle porte les repères de calage et le numéro de couche.": "Sheet margin around the support: it carries the registration marks and the layer number.",
    "Bordure de matière autour du motif (feuille dans le support) : elle protège le support et porte les croix.": "Material border around the design (sheet inside the support): it protects the support and carries the crosses.",
    "Affiche les cotes à la règle pour tracer les croix de calage sur le support (feuille posée dans le support).": "Shows ruler dimensions to draw the registration crosses on the support (sheet laid inside the support).",
    "Machine de découpe : fixe la largeur de coupe et les tapis utilisables.": "Cutting machine: sets the cutting width and the usable mats.",
    "Largeur de coupe maximale de la machine, en mm (utile surtout sans tapis, matière en rouleau).": "Maximum cutting width of the machine, in mm (mostly useful without a mat, roll material).",
    "Tapis de découpe utilisé : vérifie que la feuille tient dessus et l'affiche dans la mise en page.": "Cutting mat used: checks that the sheet fits on it and shows it in the layout.",
    "Largeur du tapis, en mm (sens d'entrée dans la machine).": "Mat width, in mm (feed direction into the machine).", "Longueur du tapis, en mm.": "Mat length, in mm.",
    "Nombre de coins portant un repère de calage. Sur 3 coins, le coin vide sert de détrompeur.": "Number of corners carrying a registration mark. With 3 corners, the empty corner acts as a key.",
    "Forme des repères : équerres sur les angles du support, croix à reporter au crayon, ou trous pour pions.": "Mark shape: L-brackets on the support corners, crosses to transfer in pencil, or peg holes.",
    "Taille des repères de calage, en mm.": "Size of the registration marks, in mm.",
    "Petites encoches carrées en haut de la feuille : leur nombre indique le numéro de la couche.": "Small square notches at the top of the sheet: their count gives the layer number.",
    "Découpe aussi le contour de la feuille (sinon seules les ouvertures et les repères sont découpés).": "Also cuts the sheet outline (otherwise only the openings and marks are cut).",
    "Nombre de pochoirs (couleurs peintes), sans compter le support nu ni le pochoir de contours.": "Number of stencils (painted colours), not counting the bare support or the outline stencil.",
    "Importance de la teinte face à la clarté pour former les couches (mode couleur). 0 % = clarté seule ; 40 % = réglage d'origine (la clarté domine) ; 100 % = équilibre perceptif ; au-delà, les couleurs différentes sont séparées même à clarté égale. Sans effet en noir et blanc ou avec des seuils manuels.": "Importance of the hue against the lightness when forming the layers (colour mode). 0 % = lightness only; 40 % = original setting (lightness dominates); 100 % = perceptual balance; above, different colours are separated even at equal lightness. No effect in black and white or with manual thresholds.",
    "Couleurs calculées des couches (bouton Auto). Elles sont mesurées sur la photo d'origine, sans le prétraitement. 0 % = moyenne des pixels de chaque ton, souvent terne (les teintes voisines, ombres et reflets se compensent) ; 100 % = même teinte et même clarté, avec la saturation des pixels les plus vifs. Ne change pas la découpe. Sans effet en noir et blanc.": "Computed layer colours (Auto button). They are measured on the original photo, without the preprocessing. 0 % = mean of the pixels of each tone, often dull (neighbouring hues, shadows and highlights average out); 100 % = same hue and lightness, with the saturation of the most vivid pixels. Does not change the cut. No effect in black and white.",
    "Niveau de détail : bas = formes simples et lisses, haut = plus de petits détails (plus de découpe et de ponts).": "Level of detail: low = simple smooth shapes, high = more small details (more cutting and bridges).",
    "Couleur, noir et blanc, ou automatique (détecté selon l'image).": "Colour, black and white, or automatic (detected from the image).",
    "Cumulatif : chaque pochoir ouvre sa couleur et toutes les plus foncées (moins de raccords). Exclusif : chaque pochoir n'ouvre que sa couleur.": "Cumulative: each stencil opens its colour and all darker ones (fewer joins). Exclusive: each stencil opens only its colour.",
    "La teinte de l'image la plus proche de la couleur du support n'a pas de pochoir : le support reste visible à la place.": "The image tone closest to the support colour has no stencil: the support shows through instead.",
    "Retrace d'un trait fin les détails estompés par la simplification et le flou de l'aérographe, dans un pochoir séparé ou dans une couche de couleur.": "Redraws with a thin line the details faded by simplification and airbrush blur, in a separate stencil or in a colour layer.",
    "Quantité de détails retenus (bas = seulement les plus marqués). Échelle progressive : de 1 % des traits candidats à 0 jusqu'à 95 % à 100, environ 10 % à 50.": "Amount of details kept (low = only the strongest). Progressive scale: from 1 % of the candidate lines at 0 to 95 % at 100, about 10 % at 50.",
    "Largeur du trait du pochoir de contours, en mm (jamais moins que l'ouverture mini du matériau).": "Line width of the outline stencil, in mm (never less than the material's minimum opening).",
    "Les traits plus courts que cette longueur sont ignorés.": "Lines shorter than this length are ignored.",
    "Couleur du trait choisie automatiquement : la teinte de l'image la plus contrastée avec le support.": "Line colour chosen automatically: the image tone with the most contrast against the support.",
    "Couleur du trait du pochoir de contours (si la couleur automatique est décochée).": "Line colour of the outline stencil (when automatic colour is unchecked).",
    "Matériau du pochoir : fixe les contraintes de découpe et les réglages machine conseillés.": "Stencil material: sets the cutting constraints and the recommended machine settings.",
    "Largeur minimale d'une ouverture découpable : les zones plus fines sont supprimées (détails supprimés, en orange).": "Minimum width of a cuttable opening: thinner areas are removed (removed details, in orange).",
    "Largeur minimale d'une bande de matière entre deux ouvertures : plus fine, elle se déchirerait.": "Minimum width of a material strip between two openings: thinner, it would tear.",
    "Surface minimale d'une ouverture ou d'un morceau de matière, en mm².": "Minimum area of an opening or a piece of material, in mm².",
    "Ajoute des ponts pour que les îlots de matière (centre d'un O…) restent attachés à la feuille.": "Adds bridges so that material islands (the centre of an O…) stay attached to the sheet.",
    "Largeur des ponts, en mm.": "Bridge width, in mm.",
    "Nombre minimal de ponts par îlot (2 ou plus = îlot mieux tenu, mais plus de ponts visibles).": "Minimum number of bridges per island (2 or more = better-held island, but more visible bridges).",
    "Au-delà de cette surface (mm²), un îlot reçoit au moins 2 ponts.": "Above this area (mm²), an island gets at least 2 bridges.",
    "Profondeur de lame conseillée (réglage Silhouette Studio).": "Recommended blade depth (Silhouette Studio setting).",
    "Force de coupe conseillée (réglage Silhouette Studio).": "Recommended cutting force (Silhouette Studio setting).",
    "Vitesse de coupe conseillée (réglage Silhouette Studio).": "Recommended cutting speed (Silhouette Studio setting).",
    "Nombre de passages de la lame.": "Number of blade passes.", "Notes libres sur ce matériau (test de coupe, astuces…).": "Free notes on this material (test cut, tips…).",
    "Tolérance de simplification des contours : plus haut = moins de nœuds, contours moins fidèles.": "Outline simplification tolerance: higher = fewer nodes, less faithful outlines.",
    "Contours en courbes de Bézier (coupe plus douce) plutôt qu'en segments droits.": "Outlines as Bézier curves (smoother cut) rather than straight segments.",
    "Flou de l'aérographe utilisé par le rendu simulé, en mm.": "Airbrush blur used by the simulated render, in mm.",
    "Résolution de calcul : plus haut = bords plus précis mais calcul plus long. Ne fait pas apparaître de détails plus fins que les contraintes du matériau.": "Computation resolution: higher = more precise edges but longer computation. Does not reveal details finer than the material constraints.",
    "Écrase le réglage sélectionné avec les valeurs actuelles (sans sélection : comme « Enregistrer sous »).": "Overwrites the selected preset with the current values (no selection: like “Save as”).",
    "Enregistre les valeurs actuelles sous un nouveau nom.": "Saves the current values under a new name.", "Renomme le réglage sélectionné.": "Renames the selected preset.",
    "Supprime le réglage sélectionné (cliquer deux fois pour confirmer).": "Deletes the selected preset (click twice to confirm).",
    "Déplier / replier la section (une seule section ouverte à la fois). Le résumé à droite rappelle les réglages.": "Expand / collapse the section (one section open at a time). The summary on the right recalls the settings.",
    "Valider": "Confirm", "Nom du réglage à enregistrer (Entrée pour valider, Échap pour annuler)": "Name of the preset to save (Enter to confirm, Esc to cancel)",
  });

  // ------------------------------------------------------------------ motifs (textes dynamiques)
  const tr = s => EN[s] !== undefined ? EN[s] : s;
  const plural = (n, w) => `${n} ${w}${+n > 1 ? "s" : ""}`;
  const SIDES = { "gauche": "left", "droit": "right", "haut": "top", "bas": "bottom" };
  const KIND_EN = { "Support": "Support", "Matériau": "Material", "Format": "Sheet format" };
  const decEN = x => x.replace(/(\d),(\d)/g, "$1.$2");
  const P = [
    [/^Calculé en ([\d.,]+) s$/, (m, s) => `Computed in ${s} s`],
    [/^Pochoir (\d+)$/, (m, n) => `Stencil ${n}`],
    [/^(★ .+) \(perso\)$/, (m, n) => `${n} (custom)`],
    [/^(\d+) couches?( \+ contours)? · dans l'ordre$/, (m, n, c) => `${plural(n, "layer")}${c ? " + outline" : ""} · in order`],
    [/^(\d+) pochoirs? · détail (\d+)(?: · teinte (\d+) %)?(?: · vivacité (\d+) %)?$/, (m, n, d, h, v) =>
      `${plural(n, "stencil")} · detail ${d}${h ? ` · hue ${h} %` : ""}${v ? ` · vividness ${v} %` : ""}`],
    [/^(\d+) pochoirs?$/, (m, n) => plural(n, "stencil")],
    [/^(\d+) pochoir\(s\) : ΔE ([\d.]+)$/, (m, n, d) => `${n} stencil(s): ΔE ${d}`],
    [/^(\d+) coins · (.+)$/, (m, n, s) => `${n} corners · ${tr(s)}`],
    [/^tol\. ([\d.]+) mm$/, (m, t) => `tol. ${t} mm`],
    [/^activé · (.+) · sens\. (\d+)$/, (m, z, s) => `enabled · ${tr(z)} · sens. ${s}`],
    [/^contraste (\d+)$/, (m, n) => `contrast ${n}`], [/^gamma ([\d.]+)$/, (m, n) => `gamma ${n}`],
    [/^saturation (\d+) %$/, (m, n) => `saturation ${n} %`], [/^netteté (\d+)$/, (m, n) => `sharpness ${n}`],
    [/^(\d+) teintes? bien distinctes? détectées? ; (\d+) teintes retenues( \(dont celle laissée au support\))? : (.+)\.$/,
      (m, a, b, c, r) => `${plural(a, "clearly distinct tone")} detected; ${b} tones kept${c ? " (including the one left to the support)" : ""}: ${trAny(r)}.`],
    [/^écart à l'original jugé bon \(ΔE ([\d.]+) ≤ ([\d.]+)\)$/, (m, a, b) => `difference from original judged good (ΔE ${a} ≤ ${b})`],
    [/^Couche (\d+)( — contours ✎)? — (#[0-9a-f]{6})$/i, (m, n, c, h) => `Layer ${n}${c ? " — outline ✎" : ""} — ${h}`],
    [/^Couche (\d+)( \(contours\))?$/, (m, n, c) => `Layer ${n}${c ? " (outline)" : ""}`],
    [/^Couche (\d+)( \(contours\))? (#[0-9a-f]{6})$/i, (m, n, c, h) => `Layer ${n}${c ? " (outline)" : ""} ${h}`],
    [/^Couche (\d+) : peinture (#[0-9a-f]{6})$/i, (m, n, h) => `Layer ${n}: paint ${h}`],
    [/^Couche (\d+) : teinte calculée$/, (m, n) => `Layer ${n}: computed tone`],
    [/^Couche (\d+) : (#[0-9a-f]{6})$/i, (m, n, h) => `Layer ${n}: ${h}`],
    [/^Couleur de la peinture de la couche (\d+) \((choisie|calculée)\) — cliquer pour changer$/,
      (m, n, k) => `Paint colour of layer ${n} (${k === "choisie" ? "chosen" : "computed"}) — click to change`],
    [/^(Masquer|Afficher) la couche (\d+)( \(contours\))?$/, (m, a, n, c) => `${a === "Masquer" ? "Hide" : "Show"} layer ${n}${c ? " (outline)" : ""}`],
    [/^(\d+) tracés · (\d+) nœuds · (\d+) îlots? · (\d+) ponts(?: · (\d+) fusions?)?$/,
      (m, a, b, c, d, e) => `${a} paths · ${b} nodes · ${plural(c, "island")} · ${d} bridges${e ? ` · ${plural(e, "merge")}` : ""}`],
    [/^Fusion acceptée jusqu'à ([\d.]+) mm² modifiés \(zone visible\), sinon un pont\.$/,
      (m, a) => `Merge accepted up to ${a} mm² changed (visible area), otherwise a bridge.`],
    [/^⚠ (\d+) îlot\(s\) sans place pour (\d+) ponts$/, (m, a, b) => `⚠ ${a} island(s) without room for ${b} bridges`],
    [/^Coupe : ([\d.]+) m · détails supprimés : ([\d.]+) %$/, (m, a, b) => `Cut: ${a} m · removed details: ${b} %`],
    [/^Palette « (.+) »$/, (m, n) => `Palette “${tr(n)}”`],
    [/^Palette « (.+) » appliquée à (\d+) couches?$/, (m, n, k) => `Palette “${tr(n)}” applied to ${plural(k, "layer")}`],
    [/^Palette « (.+) » : couleurs les plus proches de l'image sur (\d+) couches? \(écart moyen ΔE ([\d.]+)\)$/,
      (m, n, k, d) => `Palette “${tr(n)}”: colours closest to the image on ${plural(k, "layer")} (mean ΔE ${d})`],
    [/^Palette « (.+) » enregistrée \((\d+) couleurs?\)$/, (m, n, k) => `Palette “${n}” saved (${plural(k, "colour")})`],
    [/^Palette « (.+) » supprimée$/, (m, n) => `Palette “${n}” deleted`],
    [/^Supprimer la palette « (.+) »$/, (m, n) => `Delete palette “${n}”`], [/^Supprimer (.+)$/, (m, n) => `Delete ${n}`],
    [/^(.+) : (#[0-9a-f]{6}(?: · #[0-9a-f]{6})*)$/i, (m, n, c) => `${tr(n)}: ${c}`],
    [/^(Support|Matériau|Format) « (.+) » enregistré$/, (m, k, n) => `${KIND_EN[k]} “${n}” saved`],
    [/^(Support|Matériau|Format) « (.+) » renommé en « (.+) »$/, (m, k, a, b) => `${KIND_EN[k]} “${a}” renamed to “${b}”`],
    [/^(Support|Matériau|Format) « (.+) » supprimé$/, (m, k, n) => `${KIND_EN[k]} “${n}” deleted`],
    [/^« (.+) » existe déjà : il sera remplacé$/, (m, n) => `“${n}” already exists: it will be replaced`],
    [/^« (.+) » existe déjà$/, (m, n) => `“${n}” already exists`], [/^« (.+) » n'existe pas$/, (m, n) => `“${n}” does not exist`],
    [/^Tapis (\S+) × (\S+?)( \(paysage\))?( — la feuille dépasse !)?$/, (m, a, b, l, o) => `Mat ${a} × ${b}${l ? " (landscape)" : ""}${o ? " — the sheet overflows!" : ""}`],
    [/^Support (#[0-9a-f]{6})( \(remplace la teinte (#[0-9a-f]{6})\))?$/i, (m, a, r, b) => `Support ${a}${r ? ` (replaces tone ${b})` : ""}`],
    [/^(⚠ Tapis plus large que la machine \((\d+) mm\)\. )?Feuille (\d+) × (\d+) mm : (.+)$/,
      (m, w, mm, a, b, r) => `${w ? `⚠ Mat wider than the machine (${mm} mm). ` : ""}Sheet ${a} × ${b} mm: ${trAny(r)}`],
    [/^Feuille de matière (.+?)( — le pochoir dépasse !)?$/, (m, n, o) => `Material sheet ${decEN(n)}${o ? " — the stencil overflows!" : ""}`],
    [/^Pochoir (\d+) × (\d+) mm : (.+?)(\. La feuille est plus grande que le tapis : recoupez-la\.)?$/,
      (m, a, b, r, t) => `Stencil ${a} × ${b} mm: ${trAny(r) || r}${t ? ". The sheet is larger than the mat: trim it." : ""}`],
    [/^tient avec la feuille en (portrait|paysage)$/, (m, o) => `fits with the sheet in ${o === "portrait" ? "portrait" : "landscape"}`],
    [/^tient avec le tapis en (portrait|paysage)$/, (m, o) => `fits with the mat in ${o === "portrait" ? "portrait" : "landscape"}`],
    [/^Feuille (\d+) × (\d+) mm\.$/, (m, a, b) => `Sheet ${a} × ${b} mm.`],
    [/^Rouleau : largeur de coupe (\d+) mm, longueur libre\. Feuille (\d+) × (\d+) mm : (.+)$/,
      (m, w, a, b, r) => `Roll: cutting width ${w} mm, free length. Sheet ${a} × ${b} mm: ${trAny(r)}`],
    [/^Image entière \((\d+) × (\d+) px\)$/, (m, a, b) => `Whole image (${a} × ${b} px)`],
    [/^Recadré : (\d+) × (\d+) px sur (\d+) × (\d+)$/, (m, a, b, c, d) => `Cropped: ${a} × ${b} px of ${c} × ${d}`],
    [/^Support (\d+) × (\d+) mm · image (\d+) × (\d+) mm · à (-?\d+) mm du bord gauche, (-?\d+) mm du haut$/,
      (m, a, b, c, d, x, y) => `Support ${a} × ${b} mm · image ${c} × ${d} mm · ${x} mm from the left edge, ${y} mm from the top`],
    [/^Zones peintes : ([\d.]+) % de l'image — les détails clés ne sont cherchés que dedans\.$/,
      (m, p) => `Painted areas: ${p} % of the image — key details are only searched inside.`],
    [/^Sujet détouré : ([\d.]+) % de l'image — le fond \(assombri\) restera support nu\. Gomme = retirer une zone\.$/,
      (m, p) => `Subject cut out: ${p} % of the image — the (darkened) background will stay bare support. Eraser = remove an area.`],
    [/^Sujet détouré \(([\d.]+) % de l'image\)\.$/, (m, p) => `Subject cut out (${p} % of the image).`],
    [/^Sujet sélectionné : ([\d.]+) % de l'image — le fond \(assombri\) restera support nu\. Le masque est pris tel quel : retouchez-le au pinceau ou à la gomme\.$/,
      (m, p) => `Subject selected: ${p} % of the image — the (darkened) background will stay bare support. The mask is used as is: touch it up with the brush or eraser.`],
    [/^Objet ajouté : ([\d.]+) % de l'image \(recliquez dessus pour changer de découpage, Alt \+ clic pour retirer\)$/,
      (m, p) => `Object added: ${p} % of the image (click it again for another cut, Alt + click to remove)`],
    [/^Autre découpage : ([\d.]+) % de l'image \(recliquez pour en changer encore\)$/,
      (m, p) => `Another cut: ${p} % of the image (click again to change it further)`],
    [/^Objet retiré du masque \(([\d.]+) % de l'image\)$/, (m, p) => `Object removed from the mask (${p} % of the image)`],
    [/^Téléchargement du modèle de sélection impossible \((.*)\)$/, (m, e) => `Cannot download the selection model (${e})`],
    [/^Traits retenus : (\d+)$/, (m, n) => `Lines kept: ${n}`],
    [/^Traits ajoutés : (\d+) · déjà découpés : (\d+)$/, (m, a, b) => `Lines added: ${a} · already cut: ${b}`],
    [/^Traits dans les couches : aucun détail clé ajouté( dans les zones peintes du masque)?\. Augmentez la sensibilité \(actuellement (\d+)\) ou réduisez la longueur mini d'un trait\.$/,
      (m, z, s) => `Lines in the layers: no key detail added${z ? " in the painted areas of the mask" : ""}. Increase the sensitivity (currently ${s}) or reduce the minimum line length.`],
    [/^Image ajustée au support : (\d+) × (\d+) mm$/, (m, a, b) => `Image fitted to the support: ${a} × ${b} mm`],
    [/^Image ajustée (au tapis|à la feuille|à la largeur de coupe), bordure comprise : (\d+) × (\d+) mm(.*)$/,
      (m, w, a, b, x) => `Image fitted to the ${{ "au tapis": "mat", "à la feuille": "sheet", "à la largeur de coupe": "cutting width" }[w]}, border included: ${a} × ${b} mm${
        x.replace(" (feuille tournée d'un quart de tour)", " (sheet turned a quarter turn)").replace(/ \(tapis passé en (paysage|portrait)\)/, (q, o) => ` (mat switched to ${o === "paysage" ? "landscape" : "portrait"})`)}`],
    [/^Projet ouvert : (.+)$/, (m, f) => `Project opened: ${f}`], [/^Serveur injoignable : (.+)$/, (m, e) => `Server unreachable: ${e}`],
    [/^(.+) \(projet\)$/, (m, f) => `${f} (project)`],
    [/^(haut|bas)-(gauche|droite) \(hors du support\)$/, (m, a, b) => `${tr(a + "-" + b)} (outside the support)`],
    [/^Bords de la feuille \((.+) × (.+)\) : à (.+) du bord gauche, (.+) du haut, (.+) de la droite, (.+) du bas\.$/,
      (m, w, h, l, t, r, b) => `Sheet edges (${w} × ${h}): ${l} from the left edge, ${t} from the top, ${r} from the right, ${b} from the bottom.`],
    [/^Prévisualisation (avec rendu simulé|nette)(, (\d+) couche\(s\) masquée\(s\))?$/,
      (m, k, h, n) => `Preview ${k === "nette" ? "(sharp)" : "with simulated render"}${h ? `, ${n} layer(s) hidden` : ""}`],
    [/^Pochoir de contours : aucun détail clé trouvé( dans les zones peintes du masque)?\. Augmentez la sensibilité \(actuellement (\d+)\) ou réduisez la longueur mini d'un trait\.$/,
      (m, z, s) => `Outline stencil: no key detail found${z ? " in the painted mask areas" : ""}. Increase the sensitivity (currently ${s}) or reduce the minimum line length.`],
    // Engine warnings
    [/^La feuille \((\d+) × (\d+) mm\) dépasse le tapis de (\S+) × (\S+) mm( \(en paysage\))? : (.+), choisissez un tapis plus grand ou découpez en plusieurs morceaux\.$/,
      (m, a, b, c, d, l, f) => `The sheet (${a} × ${b} mm) exceeds the ${c} × ${d} mm mat${l ? " (landscape)" : ""}: ${f === "réduisez la bordure ou la taille du motif" ? "reduce the border or the design size" : "reduce the margin around the support, switch to “sheet inside the support”"}, choose a larger mat or cut it into several pieces.`],
    [/^La feuille \((\d+) × (\d+) mm\) ne tient sur le tapis de (\S+) × (\S+) mm( \(en paysage\))? qu'en la tournant d'un quart de tour : passez le tapis en (portrait|paysage) \(section Feuille du pochoir & calage\)\.$/,
      (m, a, b, c, d, l, o) => `The sheet (${a} × ${b} mm) only fits on the ${c} × ${d} mm mat${l ? " (landscape)" : ""} when turned a quarter turn: switch the mat to ${o === "portrait" ? "portrait" : "landscape"} (Stencil sheet & registration section).`],
    [/^Le tapis de (\S+) × (\S+) mm( \(en paysage\))? est plus large que la largeur de coupe de la machine \((\d+) mm\) : il ne passera pas dans la machine\.$/,
      (m, a, b, l, w) => `The ${a} × ${b} mm mat${l ? " (landscape)" : ""} is wider than the machine's cutting width (${w} mm): it will not go through the machine.`],
    [/^La feuille \((\d+) × (\d+) mm\) est plus large que la largeur de coupe de la machine \((\d+) mm\), même tournée : il faudra la découper en plusieurs morceaux\.$/,
      (m, a, b, w) => `The sheet (${a} × ${b} mm) is wider than the machine's cutting width (${w} mm), even turned: it will have to be cut into several pieces.`],
    [/^La feuille fait (\d+) mm de large, plus que la largeur de coupe \((\d+) mm\) : faites-la passer tournée d'un quart de tour dans la machine\.$/,
      (m, a, w) => `The sheet is ${a} mm wide, more than the cutting width (${w} mm): feed it turned a quarter turn.`],
    [/^La feuille déborde du support \(bord (.+)\) : elle sera posée à cheval sur le bord ; les croix hors du support ne pourront pas y être tracées\.$/,
      (m, s) => `The sheet overflows the support (${s.split(", ").map(x => SIDES[x] || x).join(", ")} edge): it will straddle the edge; crosses outside the support cannot be drawn there.`],
    [/^Marge de la feuille trop petite pour des équerres \(il faut au moins ([\d.]+) mm\) : repères en croix à la place\.$/,
      (m, a) => `Sheet margin too small for L-brackets (at least ${a} mm needed): cross marks instead.`],
    [/^Les repères sont placés dans les angles du support et risquent de chevaucher l'image : augmentez la marge de la feuille ou la marge intérieure\.$/,
      () => "The marks are placed in the support corners and may overlap the image: increase the sheet margin or the inner margin."],
    [/^Bordure de la feuille trop étroite pour les repères \((\d+) mm, il en faut (\d+)\) : ils risquent de chevaucher le motif\. Augmentez la bordure\.$/,
      (m, a, b) => `Sheet border too narrow for the marks (${a} mm, ${b} needed): they may overlap the design. Increase the border.`],
    [/^Ce zip ne contient pas l'image d'origine \(export d'une version antérieure\) : chargez l'image puis ouvrez le fichier …_infos\.json$/,
      () => "This zip does not contain the original image (export from an earlier version): load the image then open the …_infos.json file"],
  ];

  function trAny(s) {
    if (EN[s] !== undefined) return EN[s];
    for (const [re, fn] of P) { const m = s.match(re); if (m) return fn(...m); }
    // several known sentences put together
    const sent = s.match(/[^.!?]+[.!?]+(\s|$)/g);
    if (sent && sent.length > 1 && sent.join("").trim() === s.trim()) {
      const tt = sent.map(x => x.trim()).map(x => EN[x] !== undefined ? EN[x] : null);
      if (tt.every(x => x !== null)) return tt.join(" ");
    }
    // "a · b · c" summaries: each part translated separately
    if (s.includes(" · ")) {
      const parts = s.split(" · "), out = parts.map(x => EN[x] !== undefined ? EN[x] : (P.some(([re]) => re.test(x)) ? trAny(x) : null));
      if (out.some(x => x !== null)) return out.map((x, i) => x === null ? parts[i] : x).join(" · ");
    }
    return null;
  }

  // ------------------------------------------------------------------ moteur
  let LANG = "en";
  try { LANG = localStorage.getItem(LS) || "en"; } catch (e) { /* storage unavailable */ }
  const ORIG_TEXT = new WeakMap();          // text node -> original French text
  const ORIG_ATTR = new WeakMap();          // element -> { attribute: French value }
  const ATTRS = ["title", "placeholder", "aria-label", "alt", "label"];
  const PREFIX = /^([⚠●✎★＋]\s*)/;

  function translateString(s) {
    const norm = s.replace(/\s+/g, " ").trim();
    if (!norm || !/[A-Za-zÀ-ÿ]/.test(norm)) return null;
    let pre = "", core = norm;
    let r = trAny(core);
    if (r === null) {
      const m = core.match(PREFIX);
      if (m) { pre = m[1]; core = core.slice(m[1].length); r = trAny(core); }
    }
    if (r === null) return null;
    const lead = s.match(/^\s*/)[0], trail = s.match(/\s*$/)[0];
    return lead + pre + r + trail;
  }
  const skip = n => { const el = n.nodeType === 1 ? n : n.parentElement; return !el || el.closest("[data-noi18n], script, style, textarea"); };

  function doText(node) {
    if (skip(node)) return;
    const cur = node.data;
    let fr = ORIG_TEXT.get(node);
    if (fr === undefined || (cur !== fr && cur !== node.__en)) { fr = cur; ORIG_TEXT.set(node, fr); }
    if (LANG === "fr") { if (cur !== fr) node.data = fr; return; }
    const en = translateString(fr);
    node.__en = en === null ? fr : en;
    if (en !== null && cur !== en) node.data = en;
  }
  function doAttrs(el) {
    if (skip(el)) return;
    let o = ORIG_ATTR.get(el);
    if (!o) { o = {}; ORIG_ATTR.set(el, o); }
    for (const a of ATTRS) {
      if (!el.hasAttribute(a)) continue;
      const cur = el.getAttribute(a);
      if (o[a] === undefined || (cur !== o[a] && cur !== (o["__" + a]))) o[a] = cur;
      if (LANG === "fr") { if (cur !== o[a]) el.setAttribute(a, o[a]); continue; }
      const en = translateString(o[a]);
      o["__" + a] = en === null ? o[a] : en;
      if (en !== null && cur !== en) el.setAttribute(a, en);
    }
  }
  function walk(root) {
    if (!root) return;
    if (root.nodeType === 3) return doText(root);
    if (root.nodeType !== 1 && root.nodeType !== 9 && root.nodeType !== 11) return;
    if (root.nodeType === 1) doAttrs(root);
    const tw = document.createTreeWalker(root, NodeFilter.SHOW_TEXT | NodeFilter.SHOW_ELEMENT);
    let n;
    while ((n = tw.nextNode())) n.nodeType === 3 ? doText(n) : doAttrs(n);
  }

  let busy = false;
  const obs = new MutationObserver(muts => {
    if (busy) return;
    busy = true;
    try {
      for (const m of muts) {
        if (m.type === "characterData") doText(m.target);
        else if (m.type === "attributes") doAttrs(m.target);
        else m.addedNodes.forEach(walk);
      }
    } finally { busy = false; obs.takeRecords(); }
  });

  function setLang(l) {
    LANG = l === "fr" ? "fr" : "en";
    try { localStorage.setItem(LS, LANG); } catch (e) { /* storage unavailable */ }
    document.documentElement.lang = LANG;
    busy = true;
    try { walk(document.body); } finally { busy = false; obs.takeRecords(); }
    document.dispatchEvent(new CustomEvent("langchange", { detail: LANG }));
  }

  window.I18N = {
    get lang() { return LANG; },
    t: s => (LANG === "en" ? (translateString(s) ?? s) : s),
    setLang,
    start() {
      document.documentElement.lang = LANG;
      walk(document.body);
      obs.observe(document.body, { subtree: true, childList: true, characterData: true, attributes: true, attributeFilter: ATTRS });
    },
  };
})();

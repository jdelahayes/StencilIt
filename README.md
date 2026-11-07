# StencilIt

Application web locale : transforme une image (couleur ou noir & blanc) en pochoirs
multicouches pour l'aérographe, exportés en **SVG (mm)** pour Silhouette Cameo.

## Lancer

Double-cliquer sur `lancer.bat`, ou :

```
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python app.py
```

puis ouvrir http://127.0.0.1:5000

## Chaîne de traitement (`stencilit/pipeline.py`)

1. **Prétraitement** : mise à l'échelle au format réel (mm → px), lissage bilatéral selon le niveau de détail.
2. **Simplification** : k-means dans l'espace Lab (ou sur la luminance en N&B) + filtre majoritaire.
   Les couleurs sont triées du plus clair au plus foncé = ordre de pulvérisation.
3. **Couches** : cumulative (chaque pochoir ouvre sa couleur + les plus foncées) ou exclusive.
4. **Contraintes du matériau** : ouverture mini (ouverture morphologique), bande de matière mini
   (fermeture), surface mini des pièces.
5. **Ponts** : chaque îlot de matière est relié au cadre par le pont le plus court, en privilégiant
   les zones qui seront repeintes par une couche plus foncée (pont invisible). Double pont pour les grands îlots.
6. **Vectorisation** : contours lissés, simplifiés (tolérance en mm), courbes de Bézier.
7. **Export** : un SVG par couche (traits rouges 0,1 mm, repères de calage, encoches = n° de couche),
   un SVG d'aperçu, le rendu simulé et un JSON récapitulatif.

## Prévisualisation

- Onglets : **Cadrage**, **Mise en page**, **Prévisualisation**, **Comparer à l'original**, **Original**.
- La prévisualisation superpose les pochoirs réels (contraintes de découpe et ponts compris) sur la
  couleur du support, dans l'ordre de pulvérisation.
- **Rendu simulé** (case à cocher) : ajoute le flou de l'aérographe ; l'option s'applique aussi à la
  comparaison avec l'original (curseur avant/après).
- **Support dans toutes les vues** (case à côté des onglets) : toutes les vues (cadrage, mise en page,
  masque, prévisualisation, comparaison, original, pochoir) partagent le même cadre et la même échelle,
  avec le support et la feuille du pochoir (pointillés). En cadrage et masque, l'image source entière
  est posée sur le support selon le recadrage et la mise en page.
- **Masquer des couches** : boutons de la barre « Couches » ou bouton visible/masquée de chaque carte.
  La composition se fait dans le navigateur (calques transparents envoyés par le serveur) : instantané.

## Pochoir de contours (détails clés)

Option qui ajoute un pochoir supplémentaire, **peint en dernier au-dessus de toutes les couches**, pour
redessiner d'un trait fin les détails que la simplification et le flou de l'aérographe estompent.

Détection automatique (`detect_key_details`) :
1. contours candidats par Canny sur la luminance et sur les canaux de couleur (a, b) ;
2. comparaison du contraste local de l'original et du rendu simulé des autres couches : on garde les
   points où une bonne part du contraste a disparu ;
3. sélection des points les plus importants (contraste × perte) selon la **sensibilité**, suppression
   des traits plus courts que la longueur mini, épaississement à la **largeur du trait** (jamais moins que
   l'ouverture mini du matériau), puis contraintes de découpe et ponts comme les autres couches.

**Masque** (onglet « Masque contours ») : peignez au pinceau (rouge transparent) les zones où chercher
les détails clés ; gomme, taille du pinceau, « Tout effacer », raccourcis B / E / [ ]. Le masque est
stocké en coordonnées de l'image source (il suit recadrage et mise en page). Sans zone peinte, la
recherche porte sur toute l'image. Peindre active automatiquement le pochoir de contours.

Couleur du trait : automatique (teinte de la palette la plus contrastée avec le support) ou choisie
(sélecteur + nuances proposées : noir, blanc, couleurs des couches). Fichier exporté :
`…_coucheNN_surNN_contours_<couleur>.svg`.

## Support et calage

- **Support** : format, orientation et **couleur**. Formats proposés : papier ISO (A6 → A2, US Letter),
  toiles et cadres du commerce (20 × 20 → 70 × 100 cm), châssis français **Figure, Paysage et Marine**
  (0F → 120F, 1P → 120P, 1M → 120M, ex. 6F = 41 × 33 cm), ou personnalisé. L'image est
  centrée sur le support (ajustée avec une marge intérieure, ou à une largeur fixée).
  La teinte de l'image la plus proche de la couleur du support peut rester « nue » (pas de pochoir) ;
  la simulation est faite sur la couleur réelle du support.
- **Recadrage** (onglet « Cadrage ») : cadre à poignées sur l'image source, proportions libres,
  du support ou fixes (1:1, 4:3, 3:4, 16:9, 9:16). La recommandation du nombre de couches porte sur
  la partie recadrée.
- **Taille et position** (onglet « Mise en page ») : taille en % de « ajusté au support » ou en mm,
  position du centre en %, déplacement à la souris, molette pour la taille ; boutons Ajuster / Remplir /
  Centrer. Ce qui dépasse du support est rogné (fond perdu).
- **Ajuster au mieux dans le pochoir** (bouton, section *Image : cadrage & taille*) : plus grande image
  possible selon le mode de feuille — le support (marge intérieure comprise) pour une feuille autour du
  support, la feuille moins sa bordure en taille fixe, le tapis (ou la largeur de coupe sans tapis) moins
  la bordure pour une feuille ajustée au motif. L'orientation de la feuille ou du tapis qui donne la plus
  grande image est choisie automatiquement, et la feuille reste sur le support.
- **Redimensionnement au mm** : largeur et hauteur de l'image, avec ou sans conservation des
  proportions (étirement possible), ou poignée en bas à droite de l'image dans « Mise en page »
  (Maj = proportions libres).
- **Alignement sur le support** : 9 positions (coins, milieux des bords, centre) à une distance
  du bord réglable, et centrage horizontal / vertical séparé.
- **Feuille du pochoir** — trois modes (section *Feuille du pochoir & calage*) :
  - *Autour du support* : support + marge tout autour ; calage sur les angles du support (équerres)
    ou croix / trous dans la marge.
  - *Dans le support, ajustée au motif* : feuille = partie visible de l'image + bordure réglable,
    posée sur le support (grande toile, mur, meuble…).
  - *Dans le support, taille fixe* : L × H (bouton « = tapis » pour prendre la taille du tapis),
    centrée sur le motif ; un motif plus grand est rogné à l'intérieur de la bordure.
  Feuille dans le support : les équerres sont remplacées par des **croix** dans la bordure, et des
  **cotes à la règle** (depuis le coin haut-gauche du support, et depuis la droite / le bas) indiquent
  où tracer chaque croix au crayon ; on aligne ensuite chaque couche sur ces traits. Les cotes
  s'affichent sous l'aperçu (« Calage à la règle ») et dans « Mise en page » ; elles sont exportées
  dans `…_infos.json`, en commentaire de chaque SVG de coupe et en calque bleu *Cotes de calage (ne pas
  découper)* dans l'aperçu et le fichier Inkscape. Une croix hors du support est signalée.
- Un avertissement s'affiche si la feuille dépasse la largeur de coupe de la machine (305 mm pour une
  Cameo 4/5) ou le tapis choisi.
- **Machine de découpe** : Cameo 4 / Cameo 5 (305 mm de large), Cameo Pro (610 mm) ou autre machine
  (largeur saisie). Les tapis plus larges que la machine ne sont pas proposés.
- **Tapis de découpe** : *standard 12 × 12″ (304,8 × 304,8 mm)*, *long 12 × 24″ (304,8 × 609,6 mm)*,
  *Cameo Pro 24 × 24″ (609,6 × 609,6 mm)*, personnalisé, ou **sans tapis** (matière en rouleau : seule
  la largeur de coupe de la machine limite la feuille, la longueur est libre).
  **Orientation du tapis** : *Portrait* (sens d'entrée dans la machine) ou *Paysage* (tapis tourné d'un
  quart de tour sous le support ; tournez le dessin de même dans Silhouette Studio). Les contrôles « la
  feuille tient sur le tapis » en tiennent compte ; la largeur physique du tapis reste comparée à la machine.
- **Tapis dans toutes les vues** (case à côté des onglets) : le tapis (quadrillage au pouce, contour et nom,
  orange si la feuille dépasse) est affiché dans toutes les vues, dans le même cadre et à la même échelle
  que l'option « Support dans toutes les vues ». L'indication sous le choix et les avertissements disent
  si la feuille tient sur le tapis, seulement tournée d'un quart de tour, ou le dépasse. Le tapis est
  enregistré avec les supports et dans le projet exporté. Dans l'onglet « Mise en page », le tapis est
  dessiné (quadrillage au pouce, feuille posée dans son coin haut-gauche) ; son contour passe en
  pointillés orange si la feuille dépasse.
- **Repères d'alignement**, sur 3 coins (le coin bas-droit vide sert de détrompeur) ou 4 coins :
  - *équerres* : fentes en L à l'extérieur des angles du support ; on aligne chaque angle du support
    sur le coin intérieur du L ;
  - *croix* de repérage dans la marge ;
  - *trous ronds* pour pions de calage.
  Des encoches carrées en haut de la feuille indiquent le numéro de la couche.

## Projet : export et réouverture

- **Exporter les SVG + projet (.zip)** : en plus des pochoirs, le zip contient l'**image d'origine**
  (`…_original.<ext>`, fichier intact), le **masque des contours** s'il existe (`…_masque_contours.png`)
  et, dans `…_infos.json`, une clé `projet` avec l'état complet de l'interface (tous les réglages,
  recadrage, matériau et réglages de coupe, couches masquées).
- **`…_inkscape.svg`** : document Inkscape (mm) avec un calque par élément, du fond vers le dessus :
  *Support* (verrouillé) · *Image d'origine (mise en page)* — recadrée, redimensionnée et placée comme
  sur le support (verrouillé) · *Aperçu (aplats)* et *Aperçu (rendu simulé)* (masqués) · *Cotes de
  calage* (feuille dans le support) · un calque par pochoir *Couche NN/NN (#couleur)* avec ses traits
  de coupe et repères. Images intégrées en JPEG sans découpe (clip-path) : c'est la seule forme que
  Silhouette Studio affiche correctement dans un calque masqué.
- **Ouvrir un projet…** (sous la zone image, ou glisser le fichier sur la zone image) :
  - le **.zip** restaure tout : image, masque, réglages, puis recalcule les calques ;
  - le **.json** seul applique les réglages à l'image chargée ; si aucune image n'est chargée,
    ils sont gardés en attente et appliqués à la prochaine image chargée (recadrage compris).
  - un `…_infos.json` d'une version antérieure (sans clé `projet`) est accepté : les paramètres
    du moteur et les réglages de coupe sont repris.

## Réglages enregistrés

- **Supports** (section *Support à peindre*) : format, couleur, marge intérieure, marge de la feuille
  et repères de calage.
- **Matériaux** (section *Matériau & découpe*) : contraintes de découpe, ponts, réglages machine
  (lame, force, vitesse, passes, notes) et largeur de coupe ; ils apparaissent avec ★ dans la liste.
- Boutons : **Enregistrer** (écrase le réglage sélectionné ; sans sélection, ou sur un matériau fourni,
  agit comme « Enregistrer sous »), **Enregistrer sous…**, **Renommer…**, **Supprimer** (2 clics pour
  confirmer). Un indicateur « ● modifié » signale des valeurs non enregistrées.
- Ces réglages sont stockés dans `presets_utilisateur.json` (créé au premier enregistrement, modifiable à la main).
- Les **derniers réglages utilisés** sont aussi mémorisés automatiquement dans le navigateur et
  restaurés à l'ouverture (sauf taille/position propres à chaque image). Lien « Réglages par défaut »
  en haut à droite pour repartir de zéro.

## Matériaux

Les préréglages (papier épais, vinyle, Mylar) sont dans `stencilit/materials.json` ;
modifiez-les ou ajoutez-en après vos tests de coupe.

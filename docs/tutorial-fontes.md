# Fontes do tutorial de fotografia rupestre

## Registro e realce

- Registre o painel em seu contexto e faça fotografias de detalhe. Anote as condições de luz e o horário da captura. Inclua uma escala e, quando disponível, uma referência de cor para calibração. A luz oblíqua pode ajudar a registrar o relevo de gravuras. [Benjamin Smith, *Recording rock art*, Field Manual for African Archaeology, pp. 138–141](https://www.africamuseum.be/sites/default/files/media/docs/research/publications/rmca/online/documents-social-sciences-humanities/FMAA/en/HR/chapters/ENG_FMA_Chap3_HR.pdf#page=21).
- Use o realce cromático para examinar diferenças sutis na fotografia. Na expansão por decorrelação descrita por Jon Harman, a transformação separa componentes correlacionados, amplia suas variações e pode produzir uma imagem em cores falsas. Compressão JPEG intensa pode eliminar informação cromática antes do processamento. [Jon Harman, *Digital enhancement of pictographs from Baja California*, 2006](https://sandiegoarchaeology.org/baja-and-california/wp-content/uploads/2024/08/06harman.pdf).
- Compare o resultado com a fotografia de referência e com outros registros do painel. Textura da rocha, micro-sombras e ruído podem influenciar o realce. Trate contornos revelados pelo processamento como hipóteses para revisão arqueológica. Estudos de campo combinaram fotografias, fotogrametria e realce, ou compararam o RGB realçado à aquisição hiperespectral. [Robert, Petrognani e Lesvignes, 2016](https://hnhp.mnhn.fr/sites/hnhp/files/part_docs/2016_jas-r_digitalphotography_erspel.pdf), [*From RGB camera to hyperspectral imaging*, 2023](https://doi.org/10.1186/s40494-023-00940-5).
- Para reproduzir o exercício no Ocre Studio, mantenha o arquivo de entrada, anote seu hash, a região analisada, a ordem das operações, os parâmetros e a versão do aplicativo. Identifique cada derivação na legenda, incluindo recorte, redimensionamento ou realce aplicado.

## Fotografias e dados abertos

| Material | Crédito e licença | Acesso |
| --- | --- | --- |
| *Cave Painting Serra da Capivara* | LeonardoRamos, CC BY-SA 4.0 | [Ficha](https://commons.wikimedia.org/wiki/File:Cave_Painting_Serra_da_Capivara.jpg) · [JPEG de 1280 × 853](https://thumb.wikimedia.org/wikipedia/commons/thumb/6/64/Cave_Painting_Serra_da_Capivara.jpg/1280px-Cave_Painting_Serra_da_Capivara.jpg) |
| *Pinturas rupestres serra da capivara* | Josias de Melo Xavier, CC BY-SA 4.0 | [Ficha e arquivo original](https://commons.wikimedia.org/wiki/File:Pinturas_rupestres_serra_da_capivara.jpg) |
| *Pinturas Rupestres – Serra da Capivara II* | Artur Warchavchik, CC BY-SA 3.0 | [Ficha e arquivo original](https://commons.wikimedia.org/wiki/File:Pinturas_Rupestres_-_Serra_da_Capivara_II.jpg) |
| *Great Gallery*, painel rupestre | Scott Catron, CC BY-SA 3.0 | [Ficha e arquivo original](https://commons.wikimedia.org/wiki/File:GreatGalleryedit.jpg) |
| *Blue-Painted Jar from Malqata*, cerâmica arqueológica | The Metropolitan Museum of Art, [Open Access CC0](https://www.metmuseum.org/hubs/open-access) | [Ficha da peça](https://www.metmuseum.org/art/collection/search/551210) · [Imagem](https://collectionapi.metmuseum.org/api/collection/v1/iiif/551210/1180963/main-image) |
| *Swedish Rock Art Research Archives*, material digital original | Swedish Rock Art Research Archives, Universidade de Gotemburgo. O catálogo declara CC BY 4.0 para este conjunto | [Catálogo e acesso ao acervo](https://researchdata.se/en/catalogue/dataset/snd0882-1) |

As fotografias do Commons servem para exercícios de visualização. Para publicar uma adaptação, credite a autoria, inclua os links da ficha e da licença, declare as alterações e use a licença original ou uma compatível conforme os termos aplicáveis. Para itens do acervo sueco, confira a ficha individual antes do uso. Remova coordenadas dos metadados das cópias distribuídas com o tutorial. [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/), [CC BY-SA 3.0](https://creativecommons.org/licenses/by-sa/3.0/), [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).

## Exercícios incluídos no Ocre Studio

A aba **Ajuda** traz duas imagens de referência preparadas sem metadados incorporados, com orientação normalizada e regravação em JPEG. A foto da Serra da Capivara, de LeonardoRamos, e sua adaptação por separação de cores são distribuídas sob CC BY-SA 4.0. A imagem do jarro de Malqata, The Met, Rogers Fund, 1912, número 12.180.39, vem do acervo aberto do museu. A comparação do jarro usa CLAHE com limite 2.

As duas derivações foram produzidas com os mesmos operadores do editor, na imagem inteira. O [registro de proveniência](../apps/editor/static/tutorial/proveniencia.json) contém hashes do arquivo baixado, da entrada distribuída e da prévia, além das versões e parâmetros. A prática em lote copia as imagens de referência e esse registro para uma pasta de trabalho escolhida pelo usuário.

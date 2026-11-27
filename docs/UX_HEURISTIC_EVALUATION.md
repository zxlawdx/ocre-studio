# Avaliação heurística do Ocre Studio

A referência local foi renderizada no Inkscape. A composição adotada conserva duas barras superiores, explorador à esquerda, abas e fotografia ao centro, ferramentas à direita e galeria abaixo. A paleta foi ajustada para grafite neutro com ocre nos estados ativos. A referência visual foi usada para a composição e os testes gráficos usam fotografias sintéticas próprias.

Critérios de Jakob Nielsen. [Nielsen Norman Group](https://www.nngroup.com/articles/ten-usability-heuristics/)

A gravidade reflete o impacto observado antes da correção. Alta indica risco de erro em um fluxo central, média indica atrito repetido e baixa indica melhoria localizada.

| Heurística | Problema anterior | Gravidade | Solução | Evidência |
| --- | --- | --- | --- | --- |
| Visibilidade do estado | Processamento e projeto tinham pouco contexto | Alta | Barra de estado, seleção identificada, progresso e fila com estado por tarefa | Smoke GTK executa seis tarefas e verifica os estados concluídos |
| Correspondência com o trabalho | Identificadores como AdaptiveV7 e brightness dominavam o painel | Média | Nomes ligados à inspeção da fotografia e detalhes técnicos recolhíveis | Histórico mostra Brilho e o painel mostra Realce combinado |
| Controle e liberdade | ROI difícil de alterar e execução monolítica | Alta | Oito alças, deslocamento, Esc, histórico por documento, pausa e cancelamento cooperativo | Testes de coordenadas, cancelamento e persistência |
| Consistência | Menus, ajustes e técnicas tinham apresentação e densidade diferentes | Média | Tokens, abas, barras compactas, foco visível, controles nativos | Inspeção visual em duas dimensões de janela |
| Prevenção de erros | Coordenadas dependiam da prévia e derivados poderiam confundir originais | Alta | Conversão para pixels nativos, hash do original, diretório de derivados e nomes únicos | Teste de round-trip; arquivos alterados e colisões tratados |
| Reconhecimento | Cada ação dependia de escolher uma opção técnica em um formulário | Média | Técnicas com nomes e descrições, galeria, grupos e abas | Smoke navega pelo catálogo e abre duas fotografias |
| Flexibilidade e eficiência | Repetição de tarefas e ajustes | Alta | Seleção múltipla, atalhos, presets, copiar ajustes e lote multitécnica | Smoke executa duas técnicas por fotografia; teste cobre repetição de falhas |
| Estética e minimalismo | Configuração ocupava a área de inspeção | Média | Canvas neutro, controles específicos e seções recolhíveis | Capturas do editor com ROI ativa e da fila |
| Diagnóstico e recuperação | Erros genéricos ocultavam fotos ou módulos ausentes | Alta | Erros contextualizados, recuperação de tarefas e confirmação em trocas de projeto | Teste injeta uma falha e reprocessa só a entrada afetada |
| Ajuda e documentação | Atalhos, limites e origem dos métodos ficavam dispersos | Baixa | Ajuda integrada, tooltips e proveniência persistente | Inspeção do menu Ajuda e sidecar de exportação |

## Escopo da verificação

O smoke usa o WebView nativo do Vela em GTK. Ele testa abertura de projeto, duas abas, ROI, modelos reais em CPU sobre imagens sintéticas, lote, abertura de resultado, salvamento e reabertura. Testes independentes verificam coordenadas, resultados versionados e associação assíncrona por fotografia. A avaliação não substitui sessões moderadas com pesquisadores ou testes de leitor de tela em todas as plataformas.

## Medição local

Uma pasta temporária no Linux Mint com 1.000 JPEGs sintéticos de 640 × 420, distribuídos em dez subpastas, levou 0,062 s para catalogação e 0,094 s para gerar as primeiras 20 miniaturas. RSS de pico do processo do benchmark foi 45,7 MiB. A medição exclui o processo gráfico e a inferência, e usa arquivos recém-gerados no mesmo SSD.

# Build e dependências de distribuição

O Vela 0.2.2 está fixado em `b02be516871e507a2f678146cb5b8a822221883d`. A saída do `makeworkflow` serviu de base para a matriz atual. O build mantém o launcher oficial do Vela. A aplicação embarca Python e o PyTorch CPU. CUDA depende de uma instalação compatível do PyTorch para execução a partir do código-fonte.

| Perfil | Evidência e restrições |
| --- | --- |
| GTK no Linux | `doctor --gui gtk`, `buildapp --gui gtk`, PyGObject GTK 3 e WebKitGTK 4.1. O runtime de desenvolvimento foi exercitado no Linux Mint. A compatibilidade depende do WebKitGTK, GTK e glibc do ambiente alvo. |
| WebView2 no Windows | `doctor --gui native` e `buildapp --gui native --installer`; o boot valida que o PyWebView escolheu Edge Chromium, evitando fallback silencioso para MSHTML. Requer o Microsoft Edge WebView2 Runtime no sistema. O runner Windows valida o executável congelado. |
| PySide6 | O PyWebView usa QtPy, que reconhece PySide6. O Vela fixado força `QT_API=pyqt6`, importa PyQt6 no launcher gerado e valida `qtpy.PYQT6`. Trocar apenas o pacote Python deixa o build incompatível. |
| `native` no Linux | O Vela fixado resolve esse perfil para Qt6/PyQt6. Selecione GTK explicitamente. |
| `makeworkflow` | O template upstream instala PyQt6 e chama `--gui qt6`. O workflow do Ocre seleciona GTK e WebView2 e rejeita PyQt na árvore final. |

Uma melhoria proposta para o Vela é tratar o toolkit Qt e seu binding como escolhas separadas. O mesmo perfil precisa percorrer parser, doctor, dependências opcionais, plano do PyInstaller, launcher, self-test e makeworkflow. A matriz deve testar PySide6/QtWebEngine em um ambiente sem PyQt e validar a identidade congelada de cada binding. Para Windows, o perfil WebView2 pode verificar o runtime e gerar instruções de instalação no Inno Setup.

## Licenças e avisos

A licença do Ocre Studio permanece em aberto. Vela é MPL-2.0, PyWebView é BSD-3-Clause, PyTorch é BSD-3-Clause, NumPy e SciPy usam BSD-3-Clause, OpenCV usa Apache-2.0, Pillow usa HPND/MIT-CMU conforme seus avisos e PyInstaller distribui seu bootloader com a exceção de empacotamento. PyGObject e GTK são bibliotecas LGPL com componentes e avisos próprios. WebKitGTK inclui componentes LGPL, BSD e outras licenças. WebView2 é um runtime distribuído pela Microsoft sob seus próprios termos. Os wheels incluem arquivos de licença e metadados coletados em `assets/dependency-notices`. Bibliotecas do sistema permanecem sujeitas aos seus próprios avisos. A matriz oficial evita redistribuir PyQt.

O self-test do commit fixado tenta um novo bind imediatamente após fechar o servidor. Isso falhou no Linux após uma requisição bem-sucedida. A correção local em `tools.patch_vela_self_test` verifica a recusa de uma nova conexão e preserva os demais checks. O repositório do Vela não recebe alterações.

## Recursos Kokentau

Os dois ZIPs públicos são baixados da release de modelos `kokentau-v8.2-models`. Seus SHA-256 estão no manifesto fixado em `docs/manifests/kokentau-v8.2.json`. O provisionador verifica o conteúdo, carrega os tensores com `weights_only=True` e grava arquivos em `assets/native-models/kokentau` antes do build. Vela copia essa pasta para fora do executável e a inclui no instalador. O pacote público tem uma ROI vazia e exclui a metadata privada do lote, imagens, histórico de treinamento e datasets.

# Ocre Studio

Desenvolva software científico para imagens arqueológicas sob a autoria de Marinaldo da Costa Barroso Filho (zxlawdx). Preserve as atribuições de terceiros e aguarde autorização para escolher licenças de código ou pesos.

## Arquitetura

Use o scaffold e o runtime oficiais do Vela. Mantenha o monólito modular com `VelaApp` e registros explícitos de `AppConfig` em `config/wsgi.py`, configuração em `config/settings.py` e composição de serviços em `config/composition.py`. Mantenha recursos e sessões persistentes separados de views recarregáveis. Futuras sessões não devem reestruturar o Ocre Studio como um projeto genérico fora do Vela.

Delegue o CLI em `manage.py` ao Vela. Use `startproject` e `startapp` para scaffold, `collectstatic` e `assets verify` para assets, `self-test` para o runtime, `makeworkflow` para a base de CI e `buildapp` para empacotar. Confirme os argumentos na revisão fixada.

## Código e interface

Use composição e injeção de dependências em serviços com estado e funções puras para algoritmos. Mantenha responsabilidades coesas, contratos pequenos e tipos nas interfaces públicas. Use quatro espaços e prefira 100 caracteres em Python. Separe módulos JavaScript, templates e CSS por responsabilidade. Use escaping e resolução de assets do Vela. Aplique UI/UX Pro Max, Design, Design System, UI Styling e Brand antes de consolidar o editor.

## Integridade e publicação

Preserve originais, registre hashes, parâmetros, versões e sequência das operações. Carregue checkpoints com desserialização restrita e validação estrita. Mantenha pesos, dados, fotos privadas, coordenadas e credenciais fora do Git, dos caches e dos instaladores. Valide o runtime e integração, teste algoritmos com fixtures sintéticas e compare a inferência real com a referência local.

Revise o conteúdo staged antes de enviar. Use a identidade Git local do autor. Valide lint, testes, assets e binários congelados no CI. Builds Windows exigem runner Windows. Publique prereleases somente após validar os artefatos previstos e seus SHA-256.

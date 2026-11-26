# CLI oficial do Vela 0.2.2

Referência verificada no commit [b02be516](https://github.com/zxlawdx/Vela-framework/tree/b02be516871e507a2f678146cb5b8a822221883d). Use Python no ambiente virtual e execute os comandos locais na raiz do projeto.

| Comando e opções | Comportamento e requisitos |
| --- | --- |
| `vela startproject NOME` | CLI global de scaffold. Cria o projeto sob o diretório atual. Use um workspace temporário e integre os arquivos quando a raiz já existir. |
| `manage.py startapp NOME` | Gera views, template e static em `apps/NOME`. Declare o AppConfig na raiz de composição. |
| `manage.py runapp` | Chama `config.wsgi.run()`. Exige backend gráfico e assets coletados. |
| `manage.py help` | Mostra comandos. O dispatcher não implementa `--help` global. |
| `manage.py collectstatic [--yes] [--no-install] [--no-tailwind] [--minify] [--output=DIR]` | Coleta assets e gera `manifest.json`. Os hooks e requisitos Node dependem de `ASSETS`. |
| `manage.py assets verify` | Valida o shell offline e o manifesto de assets. |
| `manage.py self-test` | Testa o runtime e o servidor loopback. Código 1 indica falha nos checks. |
| `manage.py routes` | Lista as rotas dos apps declarados em `config.wsgi.INSTALLED_APPS`. |
| `manage.py shell` | Abre o shell interativo do framework. |
| `manage.py logs [LINHAS]` | Lê o log mais recente. Usa 50 linhas por padrão. |
| `manage.py version` | Exibe a versão do framework. |
| `manage.py doctor [--gui PERFIL] [--json] [--fix]` | Diagnostica dependências. Inspecione o relatório, pois o código 0 não implica que os requisitos estão instalados. `--fix` pode instalar dependências. |
| `manage.py buildapp [--gui PERFIL] [--icon ARQUIVO] [--installer] [--resolve-dependencies] [--yes] [--output DIR] [--dry-run] [--tailwind] [--wizard] [--plugins]` | Gera o bundle, relatório, arquivo portátil e instalador quando disponível. PyInstaller exige build no SO alvo. |
| `manage.py init-process:installation` | Abre assistente gráfico. O alias histórico `init-process:instalation` também existe. |
| `manage.py installapp [--bundle DIR] [--scope user\|system]` | Instala um bundle existente. O escopo de sistema pode exigir privilégios. |
| `manage.py uninstallapp --slug SLUG [--scope user\|system] [--yes]` | Remove o aplicativo instalado. |
| `manage.py makeworkflow [--force]` | Gera `.github/workflows/vela-build.yml`. Revise permissões, dependências e artefatos antes de usar. |
| `manage.py dbmigrate [--dir DIR] [--database BANCO]` | Aplica migrations ao SQLiteStore do aplicativo. |
| `manage.py checkupdates --repo DONO/REPO` | Consulta a release sob demanda e requer rede. |

Perfis GUI aceitos pelo parser de build e doctor são `auto`, `qt6`, `qt5`, `gtk` e `native`. O backend precisa existir no ambiente de destino. Use `python manage.py buildapp --gui qt6 --dry-run` para conferir a preparação e `python manage.py buildapp --gui qt6 --installer --yes` para compilar no ambiente apropriado.

O launcher local deve propagar apenas retornos inteiros como códigos de saída. Alguns handlers retornam objetos, como o relatório de `collectstatic`. Parsers argparse usam 2 para argumentos inválidos. `assets verify` deve ser executado explicitamente após a coleta.

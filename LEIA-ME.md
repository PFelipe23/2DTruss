# 2DTruss — v0.1 Desktop PySide6 (edição acumulativa)

A abertura padrão desta entrega é uma **janela PySide6** com ribbon e editor CAD 2D. Não usa navegador nem servidor web. A análise estrutural permanece Python, independente da interface.

**Leia primeiro [`LEIA-ME_DESKTOP.md`](LEIA-ME_DESKTOP.md)** para instalação por usuário, recursos, importação DXF/DWG e limitações.

No Windows:

1. Instale Python 3.10+ no perfil do usuário, caso necessário.
2. Execute `INSTALAR_DEPENDENCIAS_USUARIO.bat` (PySide6 e ezdxf, sem admin; requer rede e permissão da política de TI).
3. Execute `INICIAR_DESKTOP.bat` ou `INICIAR.bat`.

A migração conserva o contrato JSON e o motor de cálculo `poe_truss/solver.py`. Para os testes, instale `requirements-test.txt` e execute `python -m pytest -q -rs tests`.

O componente antigo Tkinter (`desktop/app.py`) e a interface web legada permanecem como referências de migração, não como launchers padrão. Nenhuma licença de software CAD proprietário acompanha o pacote.

**Validação**: testes automáticos de motor e DXF foram executados; a interface PySide6 não pôde ser aberta neste ambiente por indisponibilidade do runtime Qt; DWG via ODA, compilação do EXE Windows e confronto FTool continuam sem comprovação externa. O projeto não constitui cálculo executivo ou verificação resistente completa da NBR 14762/8800.


### Consolidação desktop v0.1 — fluxo integrado + inspeção 3D

O launcher oficial é `2DTruss.pyw` (PySide6). Foram acrescentados editores nativos de perfis, telhas/declaradas, ações, combinações, estabilidade, alternativas, diagnóstico e visualização 3D independente. Consulte `LEIA-ME_DESKTOP.md` e `docs/REVISAO_DESKTOP_3D_v09.md`. O motor continua Python 2D.

# Licenciamento do 2DTruss v0.1

O código do 2DTruss está sob a licença MIT publicada no arquivo [LICENSE](../LICENSE) do repositório. Mantenha o aviso de direitos autorais e o texto da licença nas cópias do código e do executável.

## Procedência de dados e exemplos

- O catálogo `catalogo_perfis.csv` registra a fonte e a qualidade de cada entrada. Há valores demonstrativos, geometrias idealizadas e dados atribuídos a tabelas técnicas da Gerdau. Preserve essas indicações e verifique a autorização aplicável antes de redistribuir as tabelas de terceiros.
- O pacote portátil inclui o modelo de cobertura usado na abertura e dois exemplos da treliça triangular analítica. O exemplo de tributação atribuído a Olídio fica fora do pacote. Ao contribuir, use modelos próprios ou autorizados e evite anexar textos integrais de normas, apostilas e desenhos de clientes.

## Dependências do pacote Windows

- Os componentes Qt, PySide6 Essentials e Shiboken têm licenças próprias. A edição aberta usa LGPLv3/GPLv3 de acordo com o componente. Confira os avisos, o acesso ao código-fonte correspondente e as condições de substituição das bibliotecas ao redistribuir o pacote. [Licenças do Qt](https://doc.qt.io/qt-6/licensing.html) · [Qt for Python](https://doc.qt.io/qtforpython-6/licenses.html)
- O ezdxf é distribuído sob MIT. Preserve também as licenças do Python e das bibliotecas auxiliares incluídas. O build copia os metadados e os arquivos de licença presentes nos pacotes Python selecionados para `_internal`. [Licença do ezdxf](https://ezdxf.readthedocs.io/en/stable/introduction.html)
- O conversor ODA é uma dependência externa opcional para DWG, instalada e licenciada separadamente. O pacote portátil inclui suporte DXF.

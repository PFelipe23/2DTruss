"""O comparador é testado com valores SINTÉTICOS — nunca declarados como FTool."""
import csv
import sys
import tempfile
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from poe_truss.cli import compare_ftool


class ComparisonTests(unittest.TestCase):
    def test_blank_ftool_reference_is_always_pending(self):
        sample=ROOT/'verification/FTool_A02/FTool_CONFRONTO_COMPLETO.csv'
        with self.assertRaisesRegex(ValueError,'pendente'):
            compare_ftool(sample)

    def test_synthetic_values_and_wrong_values(self):
        source=ROOT/'verification/FTool_A02/FTool_CONFRONTO_COMPLETO.csv'
        with open(source,encoding='utf-8-sig',newline='') as f:
            rows=list(csv.DictReader(f,delimiter=';'))
        for r in rows:r['valor_FTOOL_PREENCHER']=r['valor_POE']
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'SINTETICO_NAO_FTOOL.csv'
            with open(path,'w',encoding='utf-8',newline='') as f:
                wr=csv.DictWriter(f,delimiter=';',fieldnames=list(rows[0]));wr.writeheader();wr.writerows(rows)
            results=compare_ftool(path)
            self.assertTrue(all(r['aprovado'] for r in results))
            rows[0]['valor_FTOOL_PREENCHER']='9999.0'
            with open(path,'w',encoding='utf-8',newline='') as f:
                wr=csv.DictWriter(f,delimiter=';',fieldnames=list(rows[0]));wr.writeheader();wr.writerows(rows)
            results=compare_ftool(path)
            self.assertFalse(results[0]['aprovado'])

if __name__=='__main__':unittest.main()

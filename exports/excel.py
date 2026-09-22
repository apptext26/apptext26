from io import BytesIO
import pandas as pd
def library_excel(lib,diag=None):
 o=BytesIO()
 with pd.ExcelWriter(o,engine="openpyxl") as w:
  lib.to_excel(w,index=False,sheet_name="Biblioteca")
  if diag is not None:pd.DataFrame(diag).to_excel(w,index=False,sheet_name="Diagnostico")
 o.seek(0);return o.getvalue()

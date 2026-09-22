def validate(p,r):
 e=[]
 for c in ["Modelo","Talla","Pieza","Cantidad","Ancho","Largo"]:
  if c not in p:e.append(f"Falta {c} en biblioteca")
 for c in ["Modelo","Talla","Unidades"]:
  if c not in r:e.append(f"Falta {c} en requerimientos")
 return e

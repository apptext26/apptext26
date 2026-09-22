import random
from models import Block

def _first_fit(pieces, fabric_width):
    blocks = []
    for piece in pieces:
        placed = False
        for block in blocks:
            if block.used_width + piece.width <= fabric_width + 1e-9:
                block.pieces.append(piece); placed = True; break
        if not placed:
            if piece.width > fabric_width + 1e-9:
                raise ValueError(f"La pieza {piece.uid} excede el ancho de tela.")
            blocks.append(Block(len(blocks)+1, fabric_width, [piece]))
    return blocks

def _best_fit(pieces, fabric_width):
    blocks = []
    for piece in pieces:
        feasible = [b for b in blocks if b.used_width + piece.width <= fabric_width + 1e-9]
        if feasible:
            min(feasible, key=lambda b: fabric_width-(b.used_width+piece.width)).pieces.append(piece)
        else:
            if piece.width > fabric_width + 1e-9:
                raise ValueError(f"La pieza {piece.uid} excede el ancho de tela.")
            blocks.append(Block(len(blocks)+1, fabric_width, [piece]))
    return blocks

def build_distributions(pieces, fabric_width, random_iterations=20, seed=42):
    variants = []
    orders = {
        "ancho_desc": sorted(pieces, key=lambda p: (p.width, p.length), reverse=True),
        "largo_desc": sorted(pieces, key=lambda p: (p.length, p.width), reverse=True),
        "area_desc": sorted(pieces, key=lambda p: (p.area, p.width), reverse=True),
    }
    for name, ordered in orders.items():
        variants.append((name+"_first_fit", _first_fit(ordered, fabric_width)))
        variants.append((name+"_best_fit", _best_fit(ordered, fabric_width)))
    rng = random.Random(seed)
    for i in range(random_iterations):
        ordered = list(pieces); rng.shuffle(ordered)
        variants.append((f"aleatoria_{i+1}", _best_fit(ordered, fabric_width)))
    unique, seen = [], set()
    for name, blocks in variants:
        signature = tuple(sorted(tuple(sorted(p.uid for p in b.pieces)) for b in blocks))
        if signature not in seen:
            seen.add(signature); unique.append((name, blocks))
    return unique

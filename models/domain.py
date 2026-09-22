from dataclasses import dataclass, field
from typing import List, Dict

@dataclass(frozen=True)
class PieceInstance:
    uid: str
    model: str
    size: str
    piece: str
    width: float
    length: float
    rotation_allowed: bool = False

    @property
    def area(self) -> float:
        return self.width * self.length

@dataclass
class Block:
    number: int
    fabric_width: float
    pieces: List[PieceInstance] = field(default_factory=list)

    @property
    def used_width(self) -> float:
        return sum(p.width for p in self.pieces)

    @property
    def free_width(self) -> float:
        return self.fabric_width - self.used_width

    @property
    def length(self) -> float:
        return max((p.length for p in self.pieces), default=0.0)

    @property
    def area(self) -> float:
        return sum(p.area for p in self.pieces)

@dataclass
class Candidate:
    candidate_id: str
    layers: int
    repetitions: Dict[str, int]
    production: Dict[str, int]
    shortages: Dict[str, int]
    overproduction: Dict[str, int]
    blocks: List[Block]
    strategy: str
    piece_area: float
    estimated_length: float
    rectangular_efficiency: float
    demand_compliance: float
    total_score: float = 0.0

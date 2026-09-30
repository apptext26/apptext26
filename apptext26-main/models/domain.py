from dataclasses import dataclass,field
@dataclass(frozen=True)
class PieceInstance:
 uid:str; model:str; size:str; piece:str; width:float; length:float
 @property
 def area(self): return self.width*self.length
@dataclass
class Block:
 number:int; fabric_width:float; pieces:list=field(default_factory=list)
 @property
 def used_width(self): return sum(p.width for p in self.pieces)
 @property
 def free_width(self): return self.fabric_width-self.used_width
 @property
 def length(self): return max((p.length for p in self.pieces),default=0)
@dataclass
class Candidate:
 candidate_id:str; layers:int; repetitions:dict; production:dict; shortages:dict; overproduction:dict; blocks:list; strategy:str; equivalent_strategies:list; piece_area:float; estimated_length:float; rectangular_efficiency:float; demand_compliance:float; total_score:float

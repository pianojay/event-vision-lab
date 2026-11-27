extends SceneTree

const Transport = preload("res://materials/transport_models.gd")
var failed := false
var checks := 0

func _check(name: String, actual: float, expected: float, tolerance: float = 0.00002) -> void:
	checks+=1
	var passed := is_finite(actual) and absf(actual-expected)<=tolerance
	failed=failed or not passed
	print("PASS " if passed else "FAIL ",name," actual=",actual," expected=",expected)

func _initialize() -> void:
	_check("Diffusion center vs independent finite differences",Transport.subsurface_stripe(0.0,0.008,0.03,1.0,500.0,0.04),0.12087740469921374,0.000001)
	_check("Diffusion nonlocal exit",Transport.subsurface_stripe(0.03,0.008,0.03,1.0,500.0,0.04),0.013166400818478415,0.000001)
	_check("Diffusion source disabled",Transport.subsurface_stripe(0.03,0.008,0.0,1.0,500.0,0.04),0.0)
	_check("Patch geometry vs independent 4D quadrature",Transport.square_view_factor(0.2,0.3,64),0.11071581888929753)
	_check("Indirect receiver vs linear solve",Transport.indirect_receiver(3.0,0.7,0.6,0.12,0.12,16),0.04842130685484727)
	_check("Direct-only control",Transport.indirect_receiver(3.0,0.7,0.6,0.12,0.12,0),0.0)
	_check("Zero-reflectance control",Transport.indirect_receiver(3.0,0.0,0.6,0.12,0.12,16),0.0)
	_check("One-bounce transfer",Transport.indirect_receiver(3.0,0.7,0.6,0.12,0.12,1),3.0*0.7*0.6*0.12/PI)
	print("MATERIAL_TRANSPORT_RESULT ",JSON.stringify({"passed":not failed,"checks":checks,"scope":"headless pure GDScript transport numerical functions"}))
	quit(1 if failed else 0)

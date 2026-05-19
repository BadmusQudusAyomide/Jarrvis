"""Math and calculator tools for safe mathematical operations."""
import ast
import operator
import math
import logging
from app.tools.base import BaseTool, ToolSchema, ToolParameter

logger = logging.getLogger(__name__)


class CalculatorTool(BaseTool):
    
    _operators = {
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: operator.truediv,
        ast.Pow: operator.pow,
        ast.FloorDiv: operator.floordiv,
        ast.Mod: operator.mod,
        ast.USub: operator.neg,
        ast.UAdd: operator.pos,
    }
    
    _allowed_names = {
        'abs': abs,
        'round': round,
        'max': max,
        'min': min,
        'sum': sum,
        'len': len,
        'sqrt': math.sqrt,
        'sin': math.sin,
        'cos': math.cos,
        'tan': math.tan,
        'log': math.log,
        'log10': math.log10,
        'exp': math.exp,
        'floor': math.floor,
        'ceil': math.ceil,
        'pi': math.pi,
        'e': math.e,
    }
    
    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="calculate",
            description="Evaluate a mathematical expression safely. Use for any calculations including arithmetic, percentages, or complex formulas. Supports: +, -, *, /, **, sqrt(), sin(), cos(), log(), pi, e, etc.",
            parameters=[
                ToolParameter(
                    name="expression",
                    type="string",
                    description="Mathematical expression to evaluate (e.g., '2 + 2', 'sqrt(16)', '100 * 1.15', 'sin(pi/2)')",
                    required=True
                )
            ],
            return_type="string"
        )
    
    def execute(self, expression: str, **kwargs) -> str:
        try:
            # Clean expression
            expression = expression.strip()
            logger.info(f"Calculating: {expression}")
            
            # Parse and evaluate safely
            result = self._safe_eval(expression)
            logger.info(f"Result: {result}")
            
            return f"{result}"
            
        except SyntaxError as e:
            return f"Error: Invalid expression syntax - {str(e)}"
        except ZeroDivisionError:
            return "Error: Division by zero"
        except Exception as e:
            logger.error(f"Calculation failed: {str(e)}", exc_info=True)
            return f"Error: {str(e)}"
    
    def _safe_eval(self, expression: str):
        """Safely evaluate mathematical expression using AST."""
        # Parse to AST
        tree = ast.parse(expression, mode='eval')
        
        return self._eval_node(tree.body)
    
    def _eval_node(self, node):
        """Recursively evaluate AST nodes."""
        # Numbers
        if isinstance(node, ast.Constant):
            if isinstance(node.value, (int, float)):
                return node.value
            raise ValueError(f"Unsupported constant: {node.value}")
        
        if isinstance(node, ast.Num):  # Python < 3.8 compatibility
            return node.n
        
        # Binary operations (+, -, *, /, etc.)
        if isinstance(node, ast.BinOp):
            left = self._eval_node(node.left)
            right = self._eval_node(node.right)
            op_type = type(node.op)
            
            if op_type not in self._operators:
                raise ValueError(f"Unsupported operator: {op_type}")
            
            return self._operators[op_type](left, right)
        
        # Unary operations (-x, +x)
        if isinstance(node, ast.UnaryOp):
            operand = self._eval_node(node.operand)
            op_type = type(node.op)
            
            if op_type not in self._operators:
                raise ValueError(f"Unsupported unary operator: {op_type}")
            
            return self._operators[op_type](operand)
        
        # Function calls (sqrt, sin, cos, etc.)
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name):
                raise ValueError("Only simple function calls allowed")
            
            func_name = node.func.id
            if func_name not in self._allowed_names:
                raise ValueError(f"Unknown function: {func_name}")
            
            # Evaluate arguments
            args = [self._eval_node(arg) for arg in node.args]
            func = self._allowed_names[func_name]
            
            return func(*args)
        
        # Variable/constant names (pi, e)
        if isinstance(node, ast.Name):
            if node.id not in self._allowed_names:
                raise ValueError(f"Unknown constant: {node.id}")
            
            value = self._allowed_names[node.id]
            if callable(value):
                raise ValueError(f"{node.id} is a function, not a value")
            
            return value
        
        raise ValueError(f"Unsupported expression element: {type(node)}")


class UnitConversionTool(BaseTool):
    """Tool for unit conversions."""
    
    # Common conversion factors to meters
    _length_to_meters = {
        'm': 1,
        'km': 1000,
        'cm': 0.01,
        'mm': 0.001,
        'ft': 0.3048,
        'in': 0.0254,
        'yd': 0.9144,
        'mi': 1609.344,
    }
    
    # Common conversion factors to grams
    _mass_to_grams = {
        'g': 1,
        'kg': 1000,
        'mg': 0.001,
        'lb': 453.592,
        'oz': 28.3495,
    }
    
    # Temperature units (need special handling)
    _temp_units = {'c', 'f', 'k'}
    
    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="convert_units",
            description="Convert between common units (length, mass, temperature). Use for unit conversions like miles to km, pounds to kg, celsius to fahrenheit.",
            parameters=[
                ToolParameter(
                    name="value",
                    type="number",
                    description="Numeric value to convert",
                    required=True
                ),
                ToolParameter(
                    name="from_unit",
                    type="string",
                    description="Source unit (e.g., 'miles', 'pounds', 'celsius')",
                    required=True
                ),
                ToolParameter(
                    name="to_unit",
                    type="string",
                    description="Target unit (e.g., 'km', 'kg', 'fahrenheit')",
                    required=True
                )
            ],
            return_type="string"
        )
    
    def execute(self, value: float, from_unit: str, to_unit: str, **kwargs) -> str:
        try:
            # Normalize unit strings
            from_norm = self._normalize_unit(from_unit)
            to_norm = self._normalize_unit(to_unit)
            
            logger.info(f"Converting {value} {from_norm} to {to_norm}")
            
            # Temperature conversion
            if from_norm in self._temp_units and to_norm in self._temp_units:
                result = self._convert_temperature(value, from_norm, to_norm)
                return f"{value} {from_unit} = {result:.2f} {to_unit}"
            
            # Length conversion
            if from_norm in self._length_to_meters and to_norm in self._length_to_meters:
                # Convert to meters first, then to target
                meters = value * self._length_to_meters[from_norm]
                result = meters / self._length_to_meters[to_norm]
                return f"{value} {from_unit} = {result:.4f} {to_unit}"
            
            # Mass conversion
            if from_norm in self._mass_to_grams and to_norm in self._mass_to_grams:
                grams = value * self._mass_to_grams[from_norm]
                result = grams / self._mass_to_grams[to_norm]
                return f"{value} {from_unit} = {result:.4f} {to_unit}"
            
            return f"Error: Cannot convert from {from_unit} to {to_unit}. Supported: length (m, km, ft, mi...), mass (g, kg, lb, oz...), temperature (c, f, k)"
            
        except Exception as e:
            logger.error(f"Unit conversion failed: {str(e)}", exc_info=True)
            return f"Error: {str(e)}"
    
    def _normalize_unit(self, unit: str) -> str:
        """Normalize unit string to standard form."""
        unit = unit.lower().strip()
        
        # Map common variations
        aliases = {
            'meter': 'm', 'meters': 'm', 'metres': 'm',
            'kilometer': 'km', 'kilometers': 'km', 'kilometres': 'km',
            'centimeter': 'cm', 'centimeters': 'cm',
            'millimeter': 'mm', 'millimeters': 'mm',
            'foot': 'ft', 'feet': 'ft',
            'inch': 'in', 'inches': 'in',
            'yard': 'yd', 'yards': 'yd',
            'mile': 'mi', 'miles': 'mi',
            'gram': 'g', 'grams': 'g',
            'kilogram': 'kg', 'kilograms': 'kg',
            'milligram': 'mg', 'milligrams': 'mg',
            'pound': 'lb', 'pounds': 'lb',
            'ounce': 'oz', 'ounces': 'oz',
            'celsius': 'c', 'fahrenheit': 'f', 'kelvin': 'k',
        }
        
        return aliases.get(unit, unit)
    
    def _convert_temperature(self, value: float, from_unit: str, to_unit: str) -> float:
        """Convert temperature between C, F, K."""
        # Convert to Celsius first
        if from_unit == 'c':
            celsius = value
        elif from_unit == 'f':
            celsius = (value - 32) * 5 / 9
        elif from_unit == 'k':
            celsius = value - 273.15
        else:
            raise ValueError(f"Unknown temperature unit: {from_unit}")
        
        
        # Convert from Celsius to target
        if to_unit == 'c':
            return celsius
        elif to_unit == 'f':
            return (celsius * 9 / 5) + 32
        elif to_unit == 'k':
            return celsius + 273.15
        else:
            raise ValueError(f"Unknown temperature unit: {to_unit}")

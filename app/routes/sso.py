
from flask import Blueprint, current_app, g, jsonify, request

from app.utils.logger import get_logger


sso_bp = Blueprint('sso', __name__, url_prefix='/sso')
logger = get_logger(__name__)



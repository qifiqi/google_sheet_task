import json
from typing import Dict, Any, Optional
from app.models import SystemConfig, db
from app.utils.logger import get_logger

logger = get_logger(__name__)

class ConfigManager:
    """配置管理器"""
    
    def __init__(self):
        self._cache = {}
        self._app = None
        # 延迟加载配置，避免在应用上下文外初始化
        # self._load_configs()

    def init_app(self, app):
        self._app = app

    def _get_app_context(self):
        try:
            from flask import has_app_context, current_app
            if has_app_context():
                return current_app.app_context()
        except Exception:
            pass

        if self._app is not None:
            return self._app.app_context()

        return None
    
    def _load_configs(self):
        """加载所有配置到缓存"""
        try:
            ctx = self._get_app_context()
            if ctx is None:
                logger.error("加载配置失败: Working outside of application context.")
                return

            with ctx:
                configs = SystemConfig.query.all()
                for config in configs:
                    # 尝试反序列化JSON字符串
                    value = config.value
                    if isinstance(value, str) and value.startswith(('{', '[')):
                        try:
                            value = json.loads(value)
                        except (json.JSONDecodeError, TypeError):
                            pass  # 保持原始字符串
                    self._cache[config.key] = value
                logger.debug(f"加载了 {len(configs)} 个配置项")
        except Exception as e:
            logger.error(f"加载配置失败: {str(e)}")
    
    def get_config(self, key: str, default: Any = None) -> Any:
        """获取配置值"""
        # 如果缓存为空，尝试加载配置
        if not self._cache:
            self._load_configs()
        
        # 如果缓存中没有该配置，尝试从数据库重新加载
        if key not in self._cache:
            try:
                ctx = self._get_app_context()
                if ctx is None:
                    logger.error(f"从数据库加载配置失败: {key}, 错误: Working outside of application context.")
                    return default

                with ctx:
                    config = SystemConfig.query.filter_by(key=key).first()
                    if config:
                        # 尝试反序列化JSON字符串
                        value = config.value
                        if isinstance(value, str) and value.startswith(('{', '[')):
                            try:
                                value = json.loads(value)
                            except (json.JSONDecodeError, TypeError):
                                pass  # 保持原始字符串
                        self._cache[key] = value
                        return value
            except Exception as e:
                logger.error(f"从数据库加载配置失败: {key}, 错误: {str(e)}")
        
        return self._cache.get(key, default)
    
    def get_all_configs(self) -> Dict[str, Any]:
        """获取所有配置"""
        # 强制重新加载配置，确保获取最新数据
        self._load_configs()
        return self._cache.copy()
    
    def set_config(self, key: str, value: Any, description: str = None) -> bool:
        """设置配置值"""
        try:
            ctx = self._get_app_context()
            if ctx is None:
                logger.error(f"设置配置失败: {key}, 错误: Working outside of application context.")
                return False

            with ctx:
                # 转换为JSON字符串
                if isinstance(value, (dict, list)):
                    value_str = json.dumps(value, ensure_ascii=False)
                else:
                    value_str = str(value)
                
                # 查找或创建配置项
                config = SystemConfig.query.filter_by(key=key).first()
                if config:
                    config.value = value_str
                    if description:
                        config.description = description
                else:
                    config = SystemConfig(
                        key=key,
                        value=value_str,
                        description=description
                    )
                    db.session.add(config)
                
                db.session.commit()
                
                # 更新缓存
                self._cache[key] = value
                
                logger.info(f"设置配置: {key} = {value}")
                return True
            
        except Exception as e:
            logger.error(f"设置配置失败: {key}, 错误: {str(e)}")
            return False
    
    def delete_config(self, key: str) -> bool:
        """删除配置"""
        try:
            ctx = self._get_app_context()
            if ctx is None:
                logger.error(f"删除配置失败: {key}, 错误: Working outside of application context.")
                return False

            with ctx:
                config = SystemConfig.query.filter_by(key=key).first()
                if config:
                    db.session.delete(config)
                    db.session.commit()
                    
                    # 从缓存中删除
                    if key in self._cache:
                        del self._cache[key]
                    
                    logger.info(f"删除配置: {key}")
                    return True
                return False
            
        except Exception as e:
            logger.error(f"删除配置失败: {key}, 错误: {str(e)}")
            return False
    
    def update_configs(self, configs: Dict[str, Any]) -> bool:
        """批量更新配置"""
        try:
            for key, value in configs.items():
                success = self.set_config(key, value)
                if not success:
                    logger.error(f"更新配置失败: {key}")
                    return False
            
            # 强制重新加载缓存，确保其他进程/线程能获取到最新配置
            self._load_configs()
            
            logger.info(f"批量更新了 {len(configs)} 个配置项")
            return True
        except Exception as e:
            logger.error(f"批量更新配置失败: {str(e)}")
            return False
    
    def get_google_sheet_config(self) -> Dict[str, Any]:
        """获取Google Sheet相关配置"""
        # 强制刷新缓存，确保获取最新配置
        self._load_configs()

        # 基于当前缓存构造配置字典（数据库里有什么就返回什么）
        configs = self._cache.copy()

        # 兼容性处理：老版本可能把这些字段存成 dict，需要统一转换为 list
        param_positions = configs.get('parameter_positions', [])
        check_positions = configs.get('check_positions', [])
        result_positions = configs.get('result_positions', [])

        if isinstance(param_positions, dict):
            param_positions = list(param_positions.values())
        if isinstance(check_positions, dict):
            check_positions = list(check_positions.values())
        if isinstance(result_positions, dict):
            result_positions = list(result_positions.values())

        configs['parameter_positions'] = param_positions
        configs['check_positions'] = check_positions
        configs['result_positions'] = result_positions

        return configs
    
    def set_google_sheet_config(self, config: Dict[str, Any]) -> bool:
        """设置Google Sheet相关配置"""
        try:
            for key, value in config.items():
                self.set_config(key, value)
            # 强制刷新缓存
            self._load_configs()
            return True
        except Exception as e:
            logger.error(f"设置Google Sheet配置失败: {str(e)}")
            return False
    
    def refresh_cache(self):
        """强制刷新配置缓存"""
        try:
            self._load_configs()
            logger.info("配置缓存已刷新")
        except Exception as e:
            logger.error(f"刷新配置缓存失败: {str(e)}")

# 全局配置管理器实例
config_manager = None

def get_config_manager():
    """获取配置管理器实例"""
    global config_manager
    if config_manager is None:
        config_manager = ConfigManager()
    return config_manager

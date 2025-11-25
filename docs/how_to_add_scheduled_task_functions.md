# 如何添加新的定时任务函数

## 问题解答

### 1. 任务结果页面任务ID显示问题
**问题**: 任务结果页面中任务ID显示为"undefined"
**解决**: 已修复TaskResult模型的to_dict方法，添加了task_id字段

### 2. 定时任务函数在哪里创建？
定时任务的执行函数在 `app/services/scheduler_service.py` 文件中定义。

## 当前可用的定时任务函数

系统目前提供以下内置函数：

1. **cleanup_old_logs** - 清理旧日志
2. **cleanup_old_results** - 清理旧结果  
3. **cleanup_old_data** - 清理旧数据（日志+结果）

## 如何添加新的定时任务函数

### 步骤1: 在SchedulerService类中添加新函数

在 `app/services/scheduler_service.py` 文件中：

```python
def _your_new_function(self, params):
    """你的新任务函数"""
    try:
        # 从params中获取参数
        param1 = params.get('param1', 'default_value')
        param2 = params.get('param2', 10)
        
        # 执行你的业务逻辑
        # 例如：数据备份、发送通知、生成报告等
        
        logger.info(f"执行新任务成功: {param1}")
        return True
        
    except Exception as e:
        logger.error(f"执行新任务失败: {e}")
        return False
```

### 步骤2: 在_run_task_function方法中注册新函数

在同一文件的`_run_task_function`方法中添加：

```python
def _run_task_function(self, scheduled_task):
    """运行具体的任务函数"""
    try:
        function_name = scheduled_task.task_function
        params = json.loads(scheduled_task.task_params) if scheduled_task.task_params else {}
        
        # 根据任务类型执行不同的函数
        if function_name == 'cleanup_old_logs':
            return self._cleanup_old_logs(params)
        elif function_name == 'cleanup_old_results':
            return self._cleanup_old_results(params)
        elif function_name == 'cleanup_old_data':
            return self._cleanup_old_data(params)
        elif function_name == 'your_new_function':  # 添加这行
            return self._your_new_function(params)   # 添加这行
        else:
            logger.error(f"未知的任务函数: {function_name}")
            return False
```

### 步骤3: 更新前端页面选项

在 `templates/admin/scheduler.html` 文件中更新函数选择下拉框：

```html
<select class="form-select" id="taskFunction" required>
    <option value="">请选择执行函数</option>
    <option value="cleanup_old_logs">清理旧日志</option>
    <option value="cleanup_old_results">清理旧结果</option>
    <option value="cleanup_old_data">清理旧数据</option>
    <option value="your_new_function">你的新函数</option>  <!-- 添加这行 -->
</select>
```

同样在编辑模态框中也要添加：

```html
<select class="form-select" id="editTaskFunction" required>
    <option value="cleanup_old_logs">清理旧日志</option>
    <option value="cleanup_old_results">清理旧结果</option>
    <option value="cleanup_old_data">清理旧数据</option>
    <option value="your_new_function">你的新函数</option>  <!-- 添加这行 -->
</select>
```

## 示例：添加数据备份任务

### 1. 添加备份函数

```python
def _backup_database(self, params):
    """备份数据库"""
    try:
        backup_path = params.get('backup_path', '/tmp/backup')
        compress = params.get('compress', True)
        
        # 执行数据库备份逻辑
        # 这里可以调用数据库备份命令或使用相关库
        
        logger.info(f"数据库备份成功，保存到: {backup_path}")
        return True
        
    except Exception as e:
        logger.error(f"数据库备份失败: {e}")
        return False

def _send_notification(self, params):
    """发送通知"""
    try:
        message = params.get('message', '定时任务执行完成')
        webhook_url = params.get('webhook_url')
        
        if webhook_url:
            # 发送webhook通知
            import requests
            requests.post(webhook_url, json={'text': message})
        
        logger.info(f"通知发送成功: {message}")
        return True
        
    except Exception as e:
        logger.error(f"发送通知失败: {e}")
        return False
```

### 2. 注册函数

```python
elif function_name == 'backup_database':
    return self._backup_database(params)
elif function_name == 'send_notification':
    return self._send_notification(params)
```

### 3. 更新前端选项

```html
<option value="backup_database">数据库备份</option>
<option value="send_notification">发送通知</option>
```

## 任务参数说明

任务参数使用JSON格式，常见的参数类型：

```json
{
    "days": 10,                    // 数字参数
    "path": "/tmp/backup",         // 字符串参数
    "compress": true,              // 布尔参数
    "emails": ["a@b.com"],         // 数组参数
    "config": {                    // 对象参数
        "timeout": 300,
        "retry": 3
    }
}
```

## 注意事项

1. **错误处理**: 所有任务函数都应该有完整的异常处理
2. **日志记录**: 使用logger记录执行过程和结果
3. **返回值**: 函数应该返回True(成功)或False(失败)
4. **数据库事务**: 如果涉及数据库操作，注意事务管理
5. **性能考虑**: 长时间运行的任务可能会阻塞调度器
6. **参数验证**: 验证传入的参数是否有效

## 测试新函数

1. 重启应用
2. 在管理页面添加新的定时任务
3. 选择你的新函数
4. 设置合适的参数
5. 使用"立即执行"功能测试
6. 查看日志确认执行结果

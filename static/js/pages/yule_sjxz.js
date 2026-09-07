        // 食物数据库 - 包含超过130个热门菜品
        let foodDatabase = {
            chinese: {
                name: "中餐",
                icon: "🥢",
                color: "#E74C3C",
                items: [
                    "宫保鸡丁", "麻婆豆腐", "红烧肉", "鱼香肉丝", "水煮鱼", "回锅肉", "糖醋里脊", 
                    "京酱肉丝", "酸菜鱼", "辣子鸡", "小炒黄牛肉", "毛血旺", "夫妻肺片", 
                    "蒜泥白肉", "水煮牛肉", "辣炒花蛤", "干锅牛蛙", "孜然羊肉", "重庆烤鱼", 
                    "蟹黄豆腐", "白灼菜心", "上汤娃娃菜", "扬州炒饭", "葱油拌面", "红油抄手"
                ]
            },
            barbecue: {
                name: "烧烤",
                icon: "🍖",
                color: "#F39C12",
                items: [
                    "羊肉串", "牛肉串", "烤鸡翅", "烤五花肉", "烤茄子", "烤韭菜", "烤金针菇", 
                    "烤生蚝", "烤扇贝", "烤面包片", "烤土豆片", "烤玉米", "烤大虾", "烤鱿鱼", 
                    "烤肠", "烤馒头片", "烤青椒", "烤鱼豆腐", "烤面筋", "烤腰子"
                ]
            },
            xiangcuisine: {
                name: "湘菜",
                icon: "🌶️",
                color: "#C0392B",
                items: [
                    "剁椒鱼头", "小炒肉", "腊味合蒸", "毛氏红烧肉", "农家小炒肉", "酸豆角肉末", 
                    "口味牛蛙", "永州血鸭", "湘西外婆菜", "土匪猪肝", "擂辣椒皮蛋", "长沙臭豆腐"
                ]
            },
            yuecuisine: {
                name: "粤菜/烧腊",
                icon: "🍗",
                color: "#D35400",
                items: [
                    "烧鹅", "蜜汁叉烧", "白切鸡", "豉油鸡", "卤水拼盘", "煲仔饭", "干炒牛河", 
                    "虾饺", "蒸凤爪", "流沙包", "皮蛋瘦肉粥", "及第粥", "清蒸鲈鱼", "老火靓汤"
                ]
            },
            western: {
                name: "西式简餐",
                icon: "🍽️",
                color: "#3498DB",
                items: [
                    "黑椒牛排意面", "奶油培根意面", "夏威夷披萨", "芝士披萨", "美式牛肉汉堡", 
                    "炸鱼薯条", "凯撒沙拉", "金枪鱼三明治", "罗宋汤", "土豆泥", "洋葱圈", "香草烤鸡"
                ]
            },
            fastfood: {
                name: "快餐汉堡",
                icon: "🍔",
                color: "#F1C40F",
                items: [
                    "巨无霸汉堡", "香辣鸡腿堡", "板烧鸡腿堡", "牛肉芝士汉堡", "薯条", "麦辣鸡翅", 
                    "上校鸡块", "老北京鸡肉卷", "鳕鱼堡", "可乐", "九珍果汁", "巧克力圣代", "菠萝派"
                ]
            },
            japanese: {
                name: "日式料理",
                icon: "🍣",
                color: "#9B59B6",
                items: [
                    "三文鱼刺身", "甜虾刺身", "北极贝刺身", "鳗鱼饭", "牛肉丼", "猪排饭", 
                    "章鱼小丸子", "大阪烧", "日式炸鸡", "味增汤", "海草沙律", "大福", "可尔必思"
                ]
            },
            dessert: {
                name: "甜点饮品",
                icon: "🍰",
                color: "#E84393",
                items: [
                    "杨枝甘露", "珍珠奶茶", "芝士奶盖绿茶", "水果茶", "拿铁咖啡", "摩卡咖啡", 
                    "提拉米苏", "芝士蛋糕", "巧克力布朗尼", "榴莲千层", "泡芙", "蛋挞", "双皮奶", 
                    "红豆沙", "冰糖炖雪梨", "冰淇淋"
                ]
            },
            liangpi: {
                name: "小吃轻食",
                icon: "🥗",
                color: "#2ECC71",
                items: [
                    "鸡胸肉沙拉", "金枪鱼沙拉", "素食沙拉碗", "全麦三明治", "酸奶水果杯", "关东煮", 
                    "麻辣烫", "酸辣粉", "凉皮", "肉夹馍", "煎饼果子", "烤冷面", "章鱼烧", "鸡蛋灌饼"
                ]
            }
        };

        // 全局变量
        let selectedCategory = 'all';
        let selectedAnimation = 'cards';
        let selectionHistory = JSON.parse(localStorage.getItem('foodSelectionHistory')) || [];
        let editingCategory = 'chinese';
        let isEditing = false;
        let animationInProgress = false;
        let animationItems = [];

        // 页面加载完成后初始化
        document.addEventListener('DOMContentLoaded', function() {
            initApp();
        });

        // 初始化应用
        function initApp() {
            // 从本地存储加载自定义数据
            loadCustomData();
            
            // 初始化分类卡片
            renderCategoryCards();
            
            // 初始化历史记录
            renderHistory();
            
            // 初始化动画选择器
            initAnimationSelector();
            
            // 绑定事件监听器
            bindEvents();
            
            // 如果有历史记录，显示最新的一个
            if (selectionHistory.length > 0) {
                const latest = selectionHistory[0];
                showResult(latest.food, latest.category, latest.icon, false);
            }
        }

        // 初始化动画选择器
        function initAnimationSelector() {
            const options = document.querySelectorAll('.animation-option');
            options.forEach(option => {
                option.addEventListener('click', function() {
                    // 移除所有active类
                    options.forEach(opt => opt.classList.remove('active'));
                    // 给当前选项添加active类
                    this.classList.add('active');
                    // 更新选中的动画
                    selectedAnimation = this.dataset.animation;
                    
                    // 显示通知
                    showNotification(`已选择动画: ${this.querySelector('.animation-name').textContent}`, 'success');
                });
            });
        }

        // 从本地存储加载自定义数据
        function loadCustomData() {
            const savedData = localStorage.getItem('customFoodDatabase');
            if (savedData) {
                try {
                    const customData = JSON.parse(savedData);
                    // 合并默认数据和自定义数据
                    for (const category in customData) {
                        if (foodDatabase[category] && customData[category].items) {
                            foodDatabase[category].items = customData[category].items;
                        }
                    }
                } catch (e) {
                    console.error('加载自定义数据失败:', e);
                }
            }
        }

        // 保存自定义数据到本地存储
        function saveCustomData() {
            localStorage.setItem('customFoodDatabase', JSON.stringify(foodDatabase));
        }

        // 渲染分类卡片
        function renderCategoryCards() {
            const container = document.getElementById('categoryContainer');
            container.innerHTML = '';
            
            // 添加"全部"选项
            const allCard = createCategoryCard('all', '全部', '🌍', 'all');
            container.appendChild(allCard);
            
            // 为每个分类创建卡片
            for (const [key, category] of Object.entries(foodDatabase)) {
                const card = createCategoryCard(key, category.name, category.icon, category.items.length);
                container.appendChild(card);
            }
        }

        // 创建分类卡片
        function createCategoryCard(key, name, icon, count) {
            const card = document.createElement('div');
            card.className = `category-card ${selectedCategory === key ? 'active' : ''}`;
            card.dataset.category = key;
            
            card.innerHTML = `
                <span class="category-icon">${icon}</span>
                <span class="category-name">${name}</span>
                ${key !== 'all' ? `<span class="category-count" style="position: absolute; top: 2px; right: 2px; background: var(--secondary-color); color: var(--dark-color); font-size: 0.6rem; width: 16px; height: 16px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-weight: bold;">${count}</span>` : ''}
            `;
            
            card.addEventListener('click', () => selectCategory(key));
            return card;
        }

        // 选择分类
        function selectCategory(category) {
            if (animationInProgress) return;
            
            selectedCategory = category;
            
            // 更新卡片状态
            document.querySelectorAll('.category-card').forEach(card => {
                if (card.dataset.category === category) {
                    card.classList.add('active');
                } else {
                    card.classList.remove('active');
                }
            });
        }

        // 绑定事件监听器
        function bindEvents() {
            // 随机选择按钮
            document.getElementById('randomBtn').addEventListener('click', performRandomSelection);
            
            // 编辑按钮
            document.getElementById('editBtn').addEventListener('click', openEditModal);
            
            // 浮动按钮
            document.getElementById('floatingBtn').addEventListener('click', toggleFloatingPanel);
            
            // 面板标签切换
            document.querySelectorAll('.panel-tab').forEach(tab => {
                tab.addEventListener('click', function() {
                    const tabName = this.dataset.tab;
                    switchTab(tabName);
                });
            });
            
            // 弹窗关闭按钮
            document.getElementById('closeModal').addEventListener('click', closeEditModal);
            document.getElementById('cancelEdit').addEventListener('click', closeEditModal);
            
            // 弹窗保存按钮
            document.getElementById('saveEdit').addEventListener('click', saveEdits);
            
            // 点击弹窗外部关闭
            document.getElementById('editModal').addEventListener('click', function(e) {
                if (e.target === this) closeEditModal();
            });
            
            // 键盘事件：ESC关闭弹窗
            document.addEventListener('keydown', function(e) {
                if (e.key === 'Escape') {
                    if (document.getElementById('editModal').style.display === 'flex') {
                        closeEditModal();
                    }
                    if (document.getElementById('floatingPanel').style.display === 'block') {
                        toggleFloatingPanel();
                    }
                }
            });
            
            // 点击页面其他地方关闭浮动面板
            document.addEventListener('click', function(e) {
                const floatingPanel = document.getElementById('floatingPanel');
                const floatingBtn = document.getElementById('floatingBtn');
                
                if (floatingPanel.style.display === 'block' && 
                    !floatingPanel.contains(e.target) && 
                    !floatingBtn.contains(e.target)) {
                    floatingPanel.style.display = 'none';
                }
            });
        }

        // 切换浮动面板标签
        function switchTab(tabName) {
            // 更新标签状态
            document.querySelectorAll('.panel-tab').forEach(tab => {
                if (tab.dataset.tab === tabName) {
                    tab.classList.add('active');
                } else {
                    tab.classList.remove('active');
                }
            });
            
            // 显示对应内容
            document.querySelectorAll('.panel-content').forEach(content => {
                if (content.id === tabName + 'Tab') {
                    content.style.display = 'block';
                } else {
                    content.style.display = 'none';
                }
            });
        }

        // 切换浮动面板显示/隐藏
        function toggleFloatingPanel() {
            const panel = document.getElementById('floatingPanel');
            if (panel.style.display === 'block') {
                panel.style.display = 'none';
            } else {
                panel.style.display = 'block';
                // 确保显示最新历史记录
                renderHistory();
            }
        }

        // 执行随机选择
        function performRandomSelection() {
            if (animationInProgress) return;
            
            animationInProgress = true;
            
            const resultPlaceholder = document.getElementById('resultPlaceholder');
            const resultContent = document.getElementById('resultContent');
            const animationContainer = document.getElementById('animationContainer');
            
            // 隐藏之前的显示结果
            resultPlaceholder.style.display = 'none';
            resultContent.style.display = 'none';
            
            // 显示动画容器
            animationContainer.style.display = 'block';
            animationContainer.innerHTML = '';
            
            // 获取当前分类的所有食物
            const allFoods = getAllFoodsFromSelectedCategory();
            
            // 根据选择的动画类型执行不同的动画
            switch(selectedAnimation) {
                case 'cards':
                    startCardsAnimation(allFoods, animationContainer);
                    break;
                case 'bouncing':
                    startBouncingAnimation(allFoods, animationContainer);
                    break;
                case 'waterfall':
                    startWaterfallAnimation(allFoods, animationContainer);
                    break;
                case 'flip3d':
                    startFlip3DAnimation(allFoods, animationContainer);
                    break;
                case 'stars':
                    startStarsAnimation(allFoods, animationContainer);
                    break;
                default:
                    startCardsAnimation(allFoods, animationContainer);
            }
        }

        // 获取当前分类的所有食物
        function getAllFoodsFromSelectedCategory() {
            let allFoods = [];
            
            if (selectedCategory === 'all') {
                // 获取所有分类的食物
                for (const [key, category] of Object.entries(foodDatabase)) {
                    category.items.forEach(food => {
                        allFoods.push({
                            name: food,
                            category: category.name,
                            icon: category.icon,
                            color: category.color
                        });
                    });
                }
            } else {
                // 获取特定分类的食物
                const category = foodDatabase[selectedCategory];
                category.items.forEach(food => {
                    allFoods.push({
                        name: food,
                        category: category.name,
                        icon: category.icon,
                        color: category.color
                    });
                });
            }
            
            // 随机排序
            return allFoods.sort(() => Math.random() - 0.5);
        }

        // 1. 卡片浮动动画
        function startCardsAnimation(foods, container) {
            const displayFoods = foods.slice(0, 20);
            animationItems = [];
            
            displayFoods.forEach((foodObj, index) => {
                const card = document.createElement('div');
                card.className = 'floating-card';
                card.innerHTML = `
                    <div class="floating-card-icon">${foodObj.icon}</div>
                    <div class="floating-card-name">${foodObj.name}</div>
                `;
                card.style.background = `rgba(${hexToRgb(foodObj.color)}, 0.2)`;
                card.style.borderColor = `rgba(${hexToRgb(foodObj.color)}, 0.3)`;
                
                // 将菜品数据对象直接存储在DOM元素上
                card.dataset.foodName = foodObj.name;
                card.dataset.foodCategory = foodObj.category;
                card.dataset.foodIcon = foodObj.icon;
                
                const item = {
                    element: card,
                    data: foodObj,
                    x: Math.random() * (container.clientWidth - 140),
                    y: Math.random() * (container.clientHeight - 180),
                    vx: (Math.random() - 0.5) * 2.5,
                    vy: (Math.random() - 0.5) * 2.5
                };
                animationItems.push(item);
                
                card.style.left = `${item.x}px`;
                card.style.top = `${item.y}px`;
                container.appendChild(card);
                
                // 显示卡片
                setTimeout(() => {
                    card.style.opacity = '1';
                    card.style.transition = 'opacity 0.5s ease';
                }, index * 30);
            });
            
            // 开始浮动动画
            let frame = 0;
            function animate() {
                frame++;
                animationItems.forEach(item => {
                    // 更新位置
                    item.x += item.vx;
                    item.y += item.vy;
                    
                    // 边界检查
                    if (item.x < 0 || item.x > container.clientWidth - 140) {
                        item.vx *= -1;
                        item.x = Math.max(0, Math.min(item.x, container.clientWidth - 140));
                    }
                    if (item.y < 0 || item.y > container.clientHeight - 180) {
                        item.vy *= -1;
                        item.y = Math.max(0, Math.min(item.y, container.clientHeight - 180));
                    }
                    
                    // 应用位置
                    item.element.style.left = `${item.x}px`;
                    item.element.style.top = `${item.y}px`;
                    
                    // 随机改变方向
                    if (Math.random() < 0.02) {
                        item.vx = (Math.random() - 0.5) * 2.5;
                        item.vy = (Math.random() - 0.5) * 2.5;
                    }
                });
                
                // 第一阶段：浮动80帧
                if (frame < 80) {
                    requestAnimationFrame(animate);
                } else {
                    // 开始选择过程
                    startSelectionProcess(foods, container);
                }
            }
            
            // 延迟开始动画，让所有卡片先显示
            setTimeout(() => {
                animate();
            }, 400);
        }

        // 2. 弹跳球动画
        function startBouncingAnimation(foods, container) {
            const displayFoods = foods.slice(0, 15);
            animationItems = [];
            
            displayFoods.forEach((foodObj, index) => {
                const ball = document.createElement('div');
                ball.className = 'bouncing-ball';
                ball.innerHTML = foodObj.icon;
                ball.style.background = `linear-gradient(135deg, ${foodObj.color}, ${lightenColor(foodObj.color, 30)})`;
                
                // 将菜品数据对象直接存储在DOM元素上
                ball.dataset.foodName = foodObj.name;
                ball.dataset.foodCategory = foodObj.category;
                ball.dataset.foodIcon = foodObj.icon;
                
                const item = {
                    element: ball,
                    data: foodObj,
                    x: Math.random() * (container.clientWidth - 70),
                    y: container.clientHeight,
                    vx: (Math.random() - 0.5) * 6,
                    vy: -(Math.random() * 18 + 6),
                    gravity: 0.3,
                    bounce: 0.7
                };
                animationItems.push(item);
                
                ball.style.left = `${item.x}px`;
                ball.style.top = `${item.y}px`;
                container.appendChild(ball);
                
                // 显示球
                setTimeout(() => {
                    ball.style.opacity = '1';
                    ball.style.transition = 'opacity 0.5s ease';
                }, index * 80);
            });
            
            // 开始弹跳动画
            let frame = 0;
            function animate() {
                frame++;
                let allStopped = true;
                
                animationItems.forEach(item => {
                    // 应用重力
                    item.vy += item.gravity;
                    
                    // 更新位置
                    item.x += item.vx;
                    item.y += item.vy;
                    
                    // 边界检查
                    if (item.x < 0 || item.x > container.clientWidth - 70) {
                        item.vx *= -item.bounce;
                        item.x = Math.max(0, Math.min(item.x, container.clientWidth - 70));
                    }
                    if (item.y > container.clientHeight - 70) {
                        item.y = container.clientHeight - 70;
                        item.vy *= -item.bounce;
                        // 添加摩擦力
                        item.vx *= 0.95;
                    }
                    
                    // 应用位置
                    item.element.style.left = `${item.x}px`;
                    item.element.style.top = `${item.y}px`;
                    
                    // 检查是否停止
                    if (Math.abs(item.vx) > 0.1 || Math.abs(item.vy) > 0.1) {
                        allStopped = false;
                    }
                });
                
                // 弹跳80帧或所有球都停止
                if (frame < 80 && !allStopped) {
                    requestAnimationFrame(animate);
                } else {
                    // 开始选择过程
                    startSelectionProcess(foods, container);
                }
            }
            
            // 延迟开始动画
            setTimeout(() => {
                animate();
            }, 400);
        }

        // 3. 瀑布流动画
        function startWaterfallAnimation(foods, container) {
            const displayFoods = foods.slice(0, 24);
            animationItems = [];
            
            displayFoods.forEach((foodObj, index) => {
                const itemEl = document.createElement('div');
                itemEl.className = 'waterfall-item';
                itemEl.innerHTML = `
                    <div class="floating-card-icon">${foodObj.icon}</div>
                    <div class="floating-card-name">${foodObj.name}</div>
                `;
                itemEl.style.background = `rgba(${hexToRgb(foodObj.color)}, 0.2)`;
                itemEl.style.borderColor = `rgba(${hexToRgb(foodObj.color)}, 0.3)`;
                
                // 将菜品数据对象直接存储在DOM元素上
                itemEl.dataset.foodName = foodObj.name;
                itemEl.dataset.foodCategory = foodObj.category;
                itemEl.dataset.foodIcon = foodObj.icon;
                
                const item = {
                    element: itemEl,
                    data: foodObj,
                    x: (index % 6) * 130 + 20,
                    y: -150,
                    targetY: Math.floor(index / 6) * 160 + 20,
                    speed: Math.random() * 3 + 2
                };
                animationItems.push(item);
                
                itemEl.style.left = `${item.x}px`;
                itemEl.style.top = `${item.y}px`;
                container.appendChild(itemEl);
            });
            
            // 开始下落动画
            let frame = 0;
            function animate() {
                frame++;
                let allArrived = true;
                
                animationItems.forEach(item => {
                    // 如果还没到达目标位置
                    if (item.y < item.targetY) {
                        item.y += item.speed;
                        allArrived = false;
                    } else {
                        item.y = item.targetY;
                    }
                    
                    // 轻微左右摆动
                    item.x += Math.sin(frame * 0.05 + item.targetY * 0.1) * 0.5;
                    
                    // 应用位置
                    item.element.style.left = `${item.x}px`;
                    item.element.style.top = `${item.y}px`;
                    
                    // 逐渐显示
                    if (item.element.style.opacity !== '1') {
                        item.element.style.opacity = Math.min(1, frame / 30).toString();
                        item.element.style.transition = 'opacity 0.1s ease';
                    }
                });
                
                if (!allArrived || frame < 80) {
                    requestAnimationFrame(animate);
                } else {
                    // 开始选择过程
                    startSelectionProcess(foods, container);
                }
            }
            
            animate();
        }

        // 4. 3D翻转动画
        function startFlip3DAnimation(foods, container) {
            const displayFoods = foods.slice(0, 15);
            animationItems = [];
            
            displayFoods.forEach((foodObj, index) => {
                const flipCard = document.createElement('div');
                flipCard.className = 'flip-card';
                flipCard.innerHTML = `
                    <div class="flip-card-inner">
                        <div class="flip-card-front">
                            <div class="flip-card-icon">${foodObj.icon}</div>
                            <div class="flip-card-name">${foodObj.name}</div>
                        </div>
                        <div class="flip-card-back">
                            <div class="flip-card-icon">${foodObj.icon}</div>
                            <div class="flip-card-name">${foodObj.name}</div>
                        </div>
                    </div>
                `;
                
                // 将菜品数据对象直接存储在DOM元素上
                flipCard.dataset.foodName = foodObj.name;
                flipCard.dataset.foodCategory = foodObj.category;
                flipCard.dataset.foodIcon = foodObj.icon;
                
                // 计算位置（圆形排列）
                const radius = Math.min(container.clientWidth, container.clientHeight) * 0.35;
                const centerX = container.clientWidth / 2;
                const centerY = container.clientHeight / 2;
                const angle = (index / displayFoods.length) * Math.PI * 2;
                
                const item = {
                    element: flipCard,
                    inner: flipCard.querySelector('.flip-card-inner'),
                    data: foodObj,
                    index: index,
                    angle: angle,
                    x: centerX + Math.cos(angle) * radius - 75,
                    y: centerY + Math.sin(angle) * radius - 95
                };
                animationItems.push(item);
                
                flipCard.style.left = `${item.x}px`;
                flipCard.style.top = `${item.y}px`;
                container.appendChild(flipCard);
                
                // 显示卡片
                setTimeout(() => {
                    flipCard.style.opacity = '1';
                    flipCard.style.transition = 'opacity 0.5s ease';
                }, index * 60);
            });
            
            // 开始翻转动画
            let frame = 0;
            function animate() {
                frame++;
                
                // 旋转卡片
                animationItems.forEach(item => {
                    // 缓慢旋转
                    const rotation = frame * 2;
                    item.inner.style.transform = `rotateY(${rotation}deg)`;
                    
                    // 圆形运动
                    const radius = Math.min(container.clientWidth, container.clientHeight) * 0.35;
                    const centerX = container.clientWidth / 2;
                    const centerY = container.clientHeight / 2;
                    const newAngle = item.angle + frame * 0.01;
                    
                    const x = centerX + Math.cos(newAngle) * radius - 75;
                    const y = centerY + Math.sin(newAngle) * radius - 95;
                    item.element.style.left = `${x}px`;
                    item.element.style.top = `${y}px`;
                });
                
                if (frame < 100) {
                    requestAnimationFrame(animate);
                } else {
                    // 开始选择过程
                    startSelectionProcess(foods, container);
                }
            }
            
            // 延迟开始动画
            setTimeout(() => {
                animate();
            }, 400);
        }

        // 5. 星空爆炸动画
        function startStarsAnimation(foods, container) {
            // 先创建星空背景
            for (let i = 0; i < 150; i++) {
                const star = document.createElement('div');
                star.className = 'star';
                star.style.left = `${Math.random() * 100}%`;
                star.style.top = `${Math.random() * 100}%`;
                star.style.opacity = Math.random() * 0.5 + 0.5;
                container.appendChild(star);
            }
            
            const displayFoods = foods.slice(0, 12);
            animationItems = [];
            
            displayFoods.forEach((foodObj, index) => {
                const card = document.createElement('div');
                card.className = 'floating-card';
                card.innerHTML = `
                    <div class="floating-card-icon">${foodObj.icon}</div>
                    <div class="floating-card-name">${foodObj.name}</div>
                `;
                card.style.background = `rgba(${hexToRgb(foodObj.color)}, 0.2)`;
                card.style.borderColor = `rgba(${hexToRgb(foodObj.color)}, 0.3)`;
                
                // 将菜品数据对象直接存储在DOM元素上
                card.dataset.foodName = foodObj.name;
                card.dataset.foodCategory = foodObj.category;
                card.dataset.foodIcon = foodObj.icon;
                
                const centerX = container.clientWidth / 2 - 70;
                const centerY = container.clientHeight / 2 - 90;
                const item = {
                    element: card,
                    data: foodObj,
                    startX: centerX,
                    startY: centerY,
                    targetX: Math.random() * (container.clientWidth - 140),
                    targetY: Math.random() * (container.clientHeight - 180),
                    progress: 0
                };
                animationItems.push(item);
                
                card.style.left = `${centerX}px`;
                card.style.top = `${centerY}px`;
                container.appendChild(card);
                
                // 显示卡片
                setTimeout(() => {
                    card.style.opacity = '1';
                    card.style.transition = 'opacity 0.5s ease';
                }, index * 80);
            });
            
            // 开始爆炸动画
            let frame = 0;
            function animate() {
                frame++;
                
                // 爆炸效果（从中心向外扩散）
                animationItems.forEach(item => {
                    item.progress = Math.min(1, frame / 30);
                    
                    // 使用缓动函数使运动更自然
                    const easedProgress = easeOutQuad(item.progress);
                    const currentX = item.startX + (item.targetX - item.startX) * easedProgress;
                    const currentY = item.startY + (item.targetY - item.startY) * easedProgress;
                    
                    item.element.style.left = `${currentX}px`;
                    item.element.style.top = `${currentY}px`;
                    
                    // 缩放效果
                    const scale = 0.5 + easedProgress * 0.5;
                    item.element.style.transform = `scale(${scale})`;
                });
                
                if (frame < 80) {
                    requestAnimationFrame(animate);
                } else {
                    // 开始选择过程
                    startSelectionProcess(foods, container);
                }
            }
            
            // 延迟开始动画
            setTimeout(() => {
                animate();
            }, 400);
        }

        // 开始选择过程（所有动画共用）
        function startSelectionProcess(foods, container) {
            // 随机选择一个动画元素索引
            const selectedIndex = Math.floor(Math.random() * animationItems.length);
            const selectedElement = animationItems[selectedIndex].element;
            const selectedData = animationItems[selectedIndex].data;
            
            // 高亮显示被选中的元素
            animationItems.forEach((item, index) => {
                if (index === selectedIndex) {
                    // 选中的元素放大并高亮
                    item.element.style.transform = 'scale(1.8)';
                    item.element.style.zIndex = '10';
                    item.element.style.boxShadow = '0 0 40px rgba(255, 255, 255, 0.9)';
                    item.element.style.transition = 'all 0.5s ease';
                } else {
                    // 其他元素淡出
                    item.element.style.opacity = '0.2';
                    item.element.style.transform = 'scale(0.7)';
                    item.element.style.transition = 'all 0.5s ease';
                }
            });
            
            // 等待1秒后显示最终结果
            setTimeout(() => {
                completeAnimation(selectedData, container);
            }, 1000);
        }

        // 完成动画并显示结果
        function completeAnimation(finalResult, container) {
            // 隐藏动画容器
            container.style.display = 'none';
            
            // 显示结果
            showResult(finalResult.name, finalResult.category, finalResult.icon, true);
            
            // 保存到历史记录
            saveToHistory(finalResult.name, finalResult.category, finalResult.icon);
            
            // 显示通知
            showNotification(`美食选定: ${finalResult.name}`, 'success');
            
            // 重置动画状态
            animationInProgress = false;
            animationItems = [];
        }

        // 工具函数：十六进制颜色转RGB
        function hexToRgb(hex) {
            const result = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex);
            return result ? 
                `${parseInt(result[1], 16)}, ${parseInt(result[2], 16)}, ${parseInt(result[3], 16)}` : 
                '255, 107, 107';
        }

        // 工具函数：颜色变亮
        function lightenColor(color, percent) {
            const num = parseInt(color.replace('#', ''), 16);
            const amt = Math.round(2.55 * percent);
            const R = (num >> 16) + amt;
            const G = (num >> 8 & 0x00FF) + amt;
            const B = (num & 0x0000FF) + amt;
            
            return '#' + (
                0x1000000 + 
                (R < 255 ? R < 1 ? 0 : R : 255) * 0x10000 + 
                (G < 255 ? G < 1 ? 0 : G : 255) * 0x100 + 
                (B < 255 ? B < 1 ? 0 : B : 255)
            ).toString(16).slice(1);
        }

        // 缓动函数
        function easeOutQuad(t) {
            return t * (2 - t);
        }

        // 显示结果
        function showResult(food, category, icon, isFinal = true) {
            const resultPlaceholder = document.getElementById('resultPlaceholder');
            const resultContent = document.getElementById('resultContent');
            const resultElement = document.getElementById('result');
            const resultCategoryElement = document.getElementById('resultCategory');
            const resultIconElement = document.getElementById('resultIcon');
            
            if (isFinal) {
                resultContent.style.display = 'block';
                resultPlaceholder.style.display = 'none';
            }
            
            resultElement.textContent = food;
            resultCategoryElement.textContent = category;
            resultIconElement.textContent = icon;
        }

        // 保存到历史记录
        function saveToHistory(food, category, icon) {
            const historyItem = {
                food,
                category,
                icon,
                timestamp: new Date().toLocaleString('zh-CN', { 
                    hour12: false,
                    month: '2-digit',
                    day: '2-digit',
                    hour: '2-digit',
                    minute: '2-digit'
                })
            };
            
            // 添加到历史记录数组的开头
            selectionHistory.unshift(historyItem);
            
            // 限制历史记录数量
            if (selectionHistory.length > 20) {
                selectionHistory = selectionHistory.slice(0, 20);
            }
            
            // 保存到本地存储
            localStorage.setItem('foodSelectionHistory', JSON.stringify(selectionHistory));
            
            // 更新历史记录显示
            renderHistory();
        }

        // 渲染历史记录
        function renderHistory() {
            const historyList = document.getElementById('historyList');
            if (!historyList) return;
            
            historyList.innerHTML = '';
            
            if (selectionHistory.length === 0) {
                const emptyState = document.createElement('div');
                emptyState.className = 'empty-state';
                emptyState.innerHTML = `
                    <i class="fas fa-history"></i>
                    <p>暂无选择历史</p>
                `;
                historyList.appendChild(emptyState);
                return;
            }
            
            selectionHistory.forEach(item => {
                const historyItem = document.createElement('div');
                historyItem.className = 'history-item';
                
                historyItem.innerHTML = `
                    <div class="history-food">
                        <span class="history-icon">${item.icon}</span>
                        <span>${item.food}</span>
                    </div>
                    <div class="history-time">${item.timestamp}</div>
                `;
                
                historyList.appendChild(historyItem);
            });
        }

        // 打开编辑弹窗
        function openEditModal() {
            if (animationInProgress) {
                showNotification('请等待动画完成后操作', 'error');
                return;
            }
            
            const modal = document.getElementById('editModal');
            modal.style.display = 'flex';
            
            // 初始化弹窗内容
            renderCategoryTabs();
            renderFoodList();
            
            isEditing = true;
        }

        // 关闭编辑弹窗
        function closeEditModal() {
            if (!isEditing) return;
            
            const modal = document.getElementById('editModal');
            modal.style.display = 'none';
            isEditing = false;
        }

        // 保存编辑
        function saveEdits() {
            // 数据已经在修改时实时保存了，这里只是关闭弹窗
            showNotification('所有更改已保存', 'success');
            closeEditModal();
            
            // 如果有当前选中的分类，确保其菜品数量更新
            if (selectedCategory !== 'all') {
                renderCategoryCards();
            }
        }

        // 渲染分类标签
        function renderCategoryTabs() {
            const tabsContainer = document.getElementById('categoryTabs');
            tabsContainer.innerHTML = '';
            
            for (const [key, category] of Object.entries(foodDatabase)) {
                const tab = document.createElement('button');
                tab.className = `category-tab ${editingCategory === key ? 'active' : ''}`;
                tab.dataset.category = key;
                tab.innerHTML = `${category.icon} ${category.name}`;
                
                tab.addEventListener('click', () => {
                    editingCategory = key;
                    document.querySelectorAll('.category-tab').forEach(t => t.classList.remove('active'));
                    tab.classList.add('active');
                    renderFoodList();
                });
                
                tabsContainer.appendChild(tab);
            }
        }

        // 渲染菜品列表
        function renderFoodList() {
            const container = document.getElementById('foodListContainer');
            const category = foodDatabase[editingCategory];
            
            container.innerHTML = `
                <div class="food-list-title">
                    <h3><span class="category-icon">${category.icon}</span> ${category.name} 菜品</h3>
                    <button class="add-food-btn" id="addFoodBtn">
                        <i class="fas fa-plus"></i> 添加菜品
                    </button>
                </div>
                <div class="food-input-container" id="foodInputContainer" style="display: none;">
                    <input type="text" class="food-input" id="newFoodInput" placeholder="输入菜品名称...">
                    <button class="add-food-btn" id="confirmAddFood">
                        <i class="fas fa-check"></i> 确认
                    </button>
                </div>
                <div class="food-list" id="foodList"></div>
            `;
            
            // 渲染菜品列表
            const foodList = document.getElementById('foodList');
            
            if (category.items.length === 0) {
                const emptyState = document.createElement('div');
                emptyState.className = 'empty-state';
                emptyState.innerHTML = `
                    <i class="fas fa-utensils"></i>
                    <p>暂无菜品，点击"添加菜品"开始添加</p>
                `;
                foodList.appendChild(emptyState);
            } else {
                category.items.forEach((food, index) => {
                    const foodItem = document.createElement('div');
                    foodItem.className = 'food-item';
                    foodItem.innerHTML = `
                        <span class="food-name">${food}</span>
                        <div class="food-actions">
                            <button class="food-action-btn edit" data-index="${index}">
                                <i class="fas fa-edit"></i>
                            </button>
                            <button class="food-action-btn delete" data-index="${index}">
                                <i class="fas fa-trash"></i>
                            </button>
                        </div>
                    `;
                    foodList.appendChild(foodItem);
                });
            }
            
            // 绑定编辑弹窗事件
            bindEditModalEvents();
        }

        // 绑定编辑弹窗事件
        function bindEditModalEvents() {
            // 添加菜品按钮
            const addFoodBtn = document.getElementById('addFoodBtn');
            if (addFoodBtn) {
                addFoodBtn.addEventListener('click', function() {
                    document.getElementById('foodInputContainer').style.display = 'flex';
                    document.getElementById('newFoodInput').focus();
                    this.style.display = 'none';
                });
            }
            
            // 确认添加按钮
            const confirmAddBtn = document.getElementById('confirmAddFood');
            if (confirmAddBtn) {
                confirmAddBtn.addEventListener('click', addNewFood);
            }
            
            // 输入框回车事件
            const foodInput = document.getElementById('newFoodInput');
            if (foodInput) {
                foodInput.addEventListener('keypress', function(e) {
                    if (e.key === 'Enter') addNewFood();
                });
            }
            
            // 为每个菜品项的编辑和删除按钮绑定事件
            document.querySelectorAll('.food-action-btn.edit').forEach(btn => {
                btn.addEventListener('click', function() {
                    const index = parseInt(this.dataset.index);
                    editFood(index);
                });
            });
            
            document.querySelectorAll('.food-action-btn.delete').forEach(btn => {
                btn.addEventListener('click', function() {
                    const index = parseInt(this.dataset.index);
                    deleteFood(index);
                });
            });
        }

        // 添加新菜品
        function addNewFood() {
            const input = document.getElementById('newFoodInput');
            const foodName = input.value.trim();
            
            if (foodName === '') {
                showNotification('菜品名称不能为空', 'error');
                return;
            }
            
            // 检查是否已存在
            if (foodDatabase[editingCategory].items.includes(foodName)) {
                showNotification('该菜品已存在', 'error');
                return;
            }
            
            // 添加到数据库
            foodDatabase[editingCategory].items.push(foodName);
            
            // 保存到本地存储
            saveCustomData();
            
            // 重新渲染菜品列表
            renderFoodList();
            
            // 更新主界面分类卡片计数
            renderCategoryCards();
            
            // 显示通知
            showNotification(`已添加: ${foodName}`, 'success');
            
            // 重置输入框
            input.value = '';
            document.getElementById('foodInputContainer').style.display = 'none';
            document.getElementById('addFoodBtn').style.display = 'flex';
        }

        // 编辑菜品
        function editFood(index) {
            const currentFood = foodDatabase[editingCategory].items[index];
            const newFoodName = prompt(`编辑菜品名称:`, currentFood);
            
            if (newFoodName && newFoodName.trim() !== '' && newFoodName !== currentFood) {
                // 更新数据库
                foodDatabase[editingCategory].items[index] = newFoodName.trim();
                
                // 保存到本地存储
                saveCustomData();
                
                // 重新渲染菜品列表
                renderFoodList();
                
                // 显示通知
                showNotification(`已更新: ${newFoodName}`, 'success');
            }
        }

        // 删除菜品
        function deleteFood(index) {
            const foodName = foodDatabase[editingCategory].items[index];
            
            if (confirm(`确定要删除"${foodName}"吗？`)) {
                // 从数据库删除
                foodDatabase[editingCategory].items.splice(index, 1);
                
                // 保存到本地存储
                saveCustomData();
                
                // 重新渲染菜品列表
                renderFoodList();
                
                // 更新主界面分类卡片计数
                renderCategoryCards();
                
                // 显示通知
                showNotification(`已删除: ${foodName}`, 'success');
            }
        }

        // 显示通知
        function showNotification(message, type = 'success') {
            const notification = document.getElementById('notification');
            const notificationText = document.getElementById('notificationText');
            
            // 设置通知内容和样式
            notificationText.textContent = message;
            
            // 根据类型设置不同样式
            if (type === 'error') {
                notification.style.background = 'var(--gradient)';
            } else if (type === 'info') {
                notification.style.background = 'linear-gradient(135deg, #3498DB 0%, #2980B9 100%)';
            } else {
                notification.style.background = 'var(--gradient-secondary)';
            }
            
            // 显示通知
            notification.style.display = 'flex';
            
            // 3秒后自动隐藏
            setTimeout(() => {
                notification.style.animation = 'slideIn 0.4s ease reverse forwards';
                setTimeout(() => {
                    notification.style.display = 'none';
                    notification.style.animation = '';
                }, 400);
            }, 3000);
        }
    

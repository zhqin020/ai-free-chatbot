在 **Windows Subsystem for Linux (WSL)** 里运行浏览器（如 **Google Chrome** 或 **Chromium**）时，经常会弹出 **“Unlock Keyring / 解锁 keyring”** 的窗口，这是因为 Linux 的密码管理系统 **GNOME Keyring** 在尝试保存浏览器密码，但当前 session 没有自动解锁。

WSL 没有完整的 Linux 桌面登录流程，所以 **keyring 不会自动解锁**，于是每次浏览器启动就弹窗。

下面是几种常见解决方法（按推荐程度排序）。

---
 
### 永久解决（推荐）

编辑启动脚本：

```bash
sudo nano /usr/bin/google-chrome
```

找到类似：

```
exec -a "$0" "$HERE/chrome" "$@"
```

改为：

```
exec -a "$0" "$HERE/chrome" --password-store=basic "$@"
```

这样 **不会再调用 GNOME keyring，也不会弹窗**。

优点：

* 最简单
* WSL 环境最稳定

缺点：

* 密码不再用系统 keyring 加密

---

# 方法二：删除 keyring（彻底关闭）

删除 keyring 文件：

```bash
rm ~/.local/share/keyrings/*
```

然后重启 WSL：

```powershell
wsl --shutdown
```

再启动浏览器。

但如果浏览器再次调用 keyring，可能还会重新创建。

---

# 方法三：设置空密码 keyring（自动解锁）

安装 keyring：

```bash
sudo apt install gnome-keyring
```

然后：

1. 打开 keyring manager

```bash
seahorse
```

2. 修改 **Login keyring**
3. 设置 **空密码**

这样启动时不会要求解锁。

但 **WSL 有时仍然会弹窗**。

---

# 方法四：完全禁用 gnome-keyring

```bash
sudo apt remove gnome-keyring
```

不过某些 Linux GUI 程序会报 warning。

---

# 最推荐方案（WSL 实际经验）

对于 **WSL + 浏览器**：

**最好使用**

```bash
--password-store=basic
```

原因：

* WSL 没有完整桌面 session
* keyring 机制设计上依赖 Linux login manager
* basic store 最稳定

---

💡 **额外建议**

如果你是在 **WSL + GUI（WSLg）** 下跑浏览器，其实更推荐直接使用 **Windows 版浏览器**（例如 Windows Chrome），因为：

* GPU 加速更好
* 不会有 keyring 问题
* WSL 浏览器性能通常更差

---

如果你愿意，我可以再告诉你一个 **WSL 用户常用的“终极解决方案”**：

可以 **100% 永久消除 keyring 弹窗，并且不需要改浏览器参数**。
很多做 Linux/WSL 开发的人都用这个办法。

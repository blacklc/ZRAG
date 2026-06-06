# python操作规范
当项目涉及到python, 则应该遵循一下操作规范.

## 第三方依赖管理
每当项目中需要或已经执行了"pip install"命令后, 你应该自动将本次安装的第三方lib以及其版本号记录在requirements.txt中.

```注意: 绝对不要使用"pip freeze"命令来构建requirements.txt.```除非取得了用户的许可.

## 编译环境管理
若用户没有特殊需求, 请为当前项目创建一个独立的虚拟python环境来用于开发与测试工作.

## python版本
默认使用当前宿主机上的最新python版本.
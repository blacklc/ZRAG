# python操作规范
当项目涉及到python, 则应该遵循本文档中的操作规范.

## 第三方依赖管理
- 每当项目中需要或已经执行了"pip install"命令后, 你应该自动将本次安装的第三方lib以及其版本号记录在requirements.txt中.
- ```不允许使用"pip freeze"命令来构建requirements.txt.```.

## 编译环境管理
- 请为当前项目创建一个独立的虚拟python环境来用于开发与测试工作.

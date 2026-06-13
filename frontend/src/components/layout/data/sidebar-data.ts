import {
  LayoutDashboard,
  FlaskConical,
  BarChart2,
  Terminal,
  Globe,
  Settings,
  Bot,
  Bug,
  FileX,
  Lock,
  ServerOff,
  Construction,
  UserX,
  TrendingUp,
} from 'lucide-react'
import { type SidebarData } from '../types'

export const sidebarData: SidebarData = {
  user: {
    name: 'Alpha Miner',
    email: 'user@worldquant.com',
    avatar: '/avatars/shadcn.jpg',
  },
  teams: [
    {
      name: 'Alpha Mining',
      logo: TrendingUp,
      plan: 'IQC',
    },
  ],
  navGroups: [
    {
      title: '监控',
      items: [
        {
          title: '挖掘看板',
          url: '/',
          icon: LayoutDashboard,
        },
        {
          title: '可提交因子',
          url: '/alphas',
          icon: FlaskConical,
        },
        {
          title: '数据分析',
          url: '/backtest',
          icon: BarChart2,
        },
        {
          title: '平台 Alpha',
          url: '/platform',
          icon: Globe,
        },
      ],
    },
    {
      title: '操作',
      items: [
        {
          title: '脚本控制',
          url: '/control',
          icon: Terminal,
        },
        {
          title: 'AI Agent',
          url: '/agent',
          icon: Bot,
        },
      ],
    },
    {
      title: '系统',
      items: [
        {
          title: '设置',
          icon: Settings,
          items: [
            { title: '系统配置', url: '/settings' },
            { title: '外观', url: '/settings/appearance' },
          ],
        },
        {
          title: '错误页面',
          icon: Bug,
          items: [
            { title: '未授权', url: '/errors/unauthorized', icon: Lock },
            { title: '禁止访问', url: '/errors/forbidden', icon: UserX },
            { title: '页面不存在', url: '/errors/not-found', icon: FileX },
            { title: '服务器错误', url: '/errors/internal-server-error', icon: ServerOff },
            { title: '维护中', url: '/errors/maintenance-error', icon: Construction },
          ],
        },
      ],
    },
  ],
}

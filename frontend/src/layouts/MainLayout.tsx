import React from 'react';
import { NavLink } from 'react-router-dom';
import { Flex, Text, Icon } from '@gravity-ui/uikit';
import {
  House,
  Gear,
  Play,
  BookOpen,
  Sliders,
  Moon,
  Sun,
  Cloud,
  NodesRight,
  ArrowRotateRight,
} from '@gravity-ui/icons';
import { useTheme } from '@/hooks/useThemeState';

interface NavItem {
  to: string;
  label: string;
  icon: React.ReactNode;
}

const navItems: NavItem[] = [
  { to: '/', label: 'Dashboard', icon: <House /> },
  { to: '/storage-manager', label: 'Storage Manager', icon: <Cloud /> },
  { to: '/llm-proxy', label: 'LLM Proxy', icon: <NodesRight /> },
  { to: '/anytask', label: 'Anytask Sync', icon: <ArrowRotateRight /> },
  { to: '/pipelines', label: 'Pipelines', icon: <Gear /> },
  { to: '/runs', label: 'Runs', icon: <Play /> },
  { to: '/docs/pipeline', label: 'Docs', icon: <BookOpen /> },
  { to: '/settings', label: 'Settings', icon: <Sliders /> },
];

interface MainLayoutProps {
  children: React.ReactNode;
}

export default function MainLayout({ children }: MainLayoutProps) {
  const { resolved, toggle } = useTheme();

  return (
    <Flex style={{ minHeight: '100vh' }}>
      <nav
        style={{
          width: 220,
          minWidth: 220,
          background: 'var(--g-color-base-float)',
          borderRight: '1px solid var(--g-color-line-generic)',
          display: 'flex',
          flexDirection: 'column',
          padding: '24px 0',
        }}
      >
        <div style={{ padding: '0 20px 24px' }}>
          <Text variant="header-1" color="primary">
            GradeLab
          </Text>
        </div>
        <Flex direction="column" gap={1} style={{ flex: 1 }}>
          {navItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === '/'}
              style={({ isActive }) => ({
                display: 'flex',
                alignItems: 'center',
                gap: 10,
                padding: '10px 20px',
                textDecoration: 'none',
                color: isActive
                  ? 'var(--g-color-text-brand-contrast)'
                  : 'var(--g-color-text-primary)',
                background: isActive
                  ? 'var(--g-color-base-brand-hover)'
                  : 'transparent',
                borderRadius: 6,
                margin: '0 8px',
                fontWeight: isActive ? 600 : 400,
                fontSize: 14,
              })}
            >
              {item.icon}
              {item.label}
            </NavLink>
          ))}
        </Flex>
        <button
          onClick={toggle}
          aria-label={resolved === 'light' ? 'Switch to dark mode' : 'Switch to light mode'}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 10,
            padding: '10px 20px',
            margin: '0 8px',
            border: 'none',
            background: 'transparent',
            borderRadius: 6,
            cursor: 'pointer',
            color: 'var(--g-color-text-secondary)',
            fontSize: 14,
          }}
        >
          <Icon data={resolved === 'light' ? Moon : Sun} size={16} />
          {resolved === 'light' ? 'Dark mode' : 'Light mode'}
        </button>
      </nav>
      <main
        style={{
          flex: 1,
          padding: 32,
          background: 'var(--g-color-base-background)',
          overflow: 'auto',
        }}
      >
        {children}
      </main>
    </Flex>
  );
}

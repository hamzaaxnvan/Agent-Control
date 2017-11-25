import {
  Alert,
  Center,
  Modal,
  PasswordInput,
  Stack,
  Text,
  Title,
} from '@mantine/core';
import { Button } from '@rungalileo/jupiter-ds';
import { IconAlertCircle, IconLock } from '@tabler/icons-react';
import Image from 'next/image';
import type { FormEvent } from 'react';
import { useState } from 'react';

import classes from '@/core/components/login-modal.module.css';
import { useAuth } from '@/core/providers/auth-provider';

type LoginModalProps = {
  opened: boolean;
};

export function LoginModal({ opened }: LoginModalProps) {
  const { login } = useAuth();
  const [apiKey, setApiKey] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);

    const trimmed = apiKey.trim();
    if (!trimmed) {
      setError('Please enter an API key.');
      return;
    }

    setLoading(true);
    try {
      const result = await login(trimmed);
      if (!result.authenticated) {
        setError('Invalid API key. Please check and try again.');
      }
    } catch {
      setError('Unable to reach the server. Please try again later.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <Modal
      opened={opened}
      onClose={() => {}}
      withCloseButton={false}
      closeOnClickOutside={false}
      closeOnEscape={false}
      centered
      size="sm"
      overlayProps={{ backgroundOpacity: 0.6, blur: 4 }}
    >
      <form onSubmit={handleSubmit}>
        <Stack gap="lg" p="md">
          <Center>
            <span className={classes.logoWrapper}>
              <span className={classes.darkLogo}>
                <Image
                  src="/ac-logo-light.svg"
                  alt="Agent Control"
                  width={48}
                  height={48}
                />
              </span>
              <span className={classes.lightLogo}>
                <Image
                  src="/ac-logo-dark.svg"
                  alt="Agent Control"
                  width={48}
                  height={48}
                />
              </span>
            </span>
          </Center>

          <Stack gap={4} ta="center">

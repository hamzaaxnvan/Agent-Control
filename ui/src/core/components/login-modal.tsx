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

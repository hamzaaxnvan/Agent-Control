import { Box, Center, Loader, Stack, Text } from '@mantine/core';
import { useRouter } from 'next/router';
import { type ReactElement, useEffect } from 'react';

import { AppLayout } from '@/core/layouts/app-layout';
import AgentDetailPage from '@/core/page-components/agent-detail/agent-detail';
import type { NextPageWithLayout } from '@/core/types/page';


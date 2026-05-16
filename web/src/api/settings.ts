import apiClient from './index';
import { toCamelCase } from './utils';

export interface RuntimeSettingOption {
  value: string;
  label: string;
}

export interface RuntimeSettingField {
  key: string;
  label: string;
  description?: string | null;
  inputType: 'text' | 'password' | 'number' | 'boolean' | 'select';
  value: string;
  placeholder?: string | null;
  secret: boolean;
  requiresRestart: boolean;
  options: RuntimeSettingOption[];
}

export interface RuntimeSettingSection {
  id: string;
  title: string;
  description?: string | null;
  fields: RuntimeSettingField[];
}

export interface RuntimeSettingsResponse {
  envFile: string;
  sections: RuntimeSettingSection[];
  validationIssues: string[];
}

export interface RuntimeSettingsUpdateResponse {
  message: string;
  updatedKeys: string[];
  restartRequiredKeys: string[];
  validationIssues: string[];
}

export const settingsApi = {
  async getRuntimeSettings(): Promise<RuntimeSettingsResponse> {
    const response = await apiClient.get<Record<string, unknown>>('/api/v1/settings');
    return toCamelCase<RuntimeSettingsResponse>(response.data);
  },

  async updateRuntimeSettings(values: Record<string, string>): Promise<RuntimeSettingsUpdateResponse> {
    const response = await apiClient.put<Record<string, unknown>>('/api/v1/settings', { values });
    return toCamelCase<RuntimeSettingsUpdateResponse>(response.data);
  },
};

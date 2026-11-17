import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import {
  fetchCurrentUser,
  getGoogleLoginUrl,
  loginWithMock as apiLoginWithMock,
  updateProfile as apiUpdateProfile,
  logoutUser,
  deleteUserAccount
} from '../services/api';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isProfileModalOpen, setIsProfileModalOpen] = useState(false);
  const [authError, setAuthError] = useState(null);

  const checkUser = useCallback(async () => {
    try {
      setIsLoading(true);
      const currentUser = await fetchCurrentUser();
      setUser(currentUser);
      if (currentUser && !currentUser.profile_complete) {
        setIsProfileModalOpen(true);
      }
    } catch (err) {
      setUser(null);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    checkUser();
  }, [checkUser]);

  const loginWithGoogle = () => {
    window.location.href = getGoogleLoginUrl();
  };

  const loginWithMock = async (opts) => {
    setIsLoading(true);
    setAuthError(null);
    try {
      const res = await apiLoginWithMock(opts);
      await checkUser();
      return res;
    } catch (err) {
      setAuthError(err.message);
      throw err;
    } finally {
      setIsLoading(false);
    }
  };

  const updateUserProfile = async (profileData) => {
    setAuthError(null);
    try {
      const res = await apiUpdateProfile(profileData);
      await checkUser();
      setIsProfileModalOpen(false);
      return res;
    } catch (err) {
      setAuthError(err.message);
      throw err;
    }
  };

  const logout = async () => {
    try {
      await logoutUser();
    } finally {
      setUser(null);
      setIsProfileModalOpen(false);
    }
  };

  const deleteAccount = async () => {
    try {
      await deleteUserAccount();
    } finally {
      setUser(null);
      setIsProfileModalOpen(false);
    }
  };

  const value = {
    user,
    isLoading,
    isProfileModalOpen,
    setIsProfileModalOpen,
    authError,
    setAuthError,
    checkUser,
    loginWithGoogle,
    loginWithMock,
    updateUserProfile,
    logout,
    deleteAccount
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}

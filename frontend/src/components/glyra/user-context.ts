import { createContext, useContext } from "react";

export type UserCtx = { name: string; setUserName: (n: string) => void };
export const UserContext = createContext<UserCtx>({ name: "Alex Morgan", setUserName: () => {} });
export const useUser = () => useContext(UserContext);
